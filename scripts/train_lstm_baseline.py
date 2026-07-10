from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING


from sklearn.metrics import r2_score, mean_absolute_error
import numpy as np
import torch
from torch.utils.data import DataLoader

from geomf import LSTMBaseline, LSTMBaselineConfig
from geomf.data import GeomagForecastDataset, prepare_geomag_cache
from geomf.losses import total_loss

if TYPE_CHECKING:
    from torch.utils.tensorboard import SummaryWriter


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def create_tensorboard_writer(args: argparse.Namespace) -> SummaryWriter | None:
    if args.disable_tensorboard:
        return None
    try:
        from torch.utils.tensorboard import SummaryWriter as TorchSummaryWriter
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "TensorBoard logging requires the 'tensorboard' package. "
            "Install it in your training environment or run with --disable_tensorboard."
        ) from exc

    log_dir = Path(args.log_dir) / args.run_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return TorchSummaryWriter(log_dir=str(log_dir))


def build_loaders(args: argparse.Namespace) -> tuple[DataLoader, DataLoader, DataLoader]:
    common = dict(
        cache_path=args.cache_path,
        seq_len=args.seq_len,
        pred_len=args.pred_len,
        split_ratios=tuple(args.split_ratios),
    )
    train_ds = GeomagForecastDataset(**common, split="train", step=args.train_step, max_samples=args.max_train_samples)
    val_ds = GeomagForecastDataset(**common, split="val", step=args.eval_step, max_samples=args.max_eval_samples)
    test_ds = GeomagForecastDataset(**common, split="test", step=args.eval_step, max_samples=args.max_eval_samples)

    loader_kwargs = dict(num_workers=args.num_workers, pin_memory=torch.cuda.is_available())
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, drop_last=True, **loader_kwargs)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, drop_last=False, **loader_kwargs)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, drop_last=False, **loader_kwargs)
    return train_loader, val_loader, test_loader


def move_batch(batch: dict[str, torch.Tensor], device: torch.device) -> dict[str, torch.Tensor]:
    return {k: v.to(device=device, dtype=torch.float32, non_blocking=True) for k, v in batch.items()}


def current_lr(optimizer: torch.optim.Optimizer) -> float:
    return float(optimizer.param_groups[0]["lr"])


def count_parameters(model: torch.nn.Module) -> tuple[int, int]:
    total = sum(param.numel() for param in model.parameters())
    trainable = sum(param.numel() for param in model.parameters() if param.requires_grad)
    return total, trainable


def describe_dataset(
    args: argparse.Namespace,
    train_loader: DataLoader,
    val_loader: DataLoader,
    test_loader: DataLoader,
    writer: SummaryWriter | None,
) -> None:
    csv_path = Path(args.csv_path)
    mode = "multistation_kp" if csv_path.is_dir() else "single_series"
    dataset_summary = {
        "data_mode": mode,
        "csv_path": str(csv_path),
        "cache_path": str(args.cache_path),
        "train_windows": len(train_loader.dataset),
        "val_windows": len(val_loader.dataset),
        "test_windows": len(test_loader.dataset),
        "batch_size": args.batch_size,
        "seq_len": args.seq_len,
        "pred_len": args.pred_len,
        "hidden_dim": args.hidden_dim,
        "num_layers": args.num_layers,
        "dropout": args.dropout,
        "train_step": args.train_step,
        "eval_step": args.eval_step,
        "max_train_samples": args.max_train_samples,
        "max_eval_samples": args.max_eval_samples,
        "device": args.device,
    }
    print(json.dumps(dataset_summary, ensure_ascii=True))

    sample = train_loader.dataset[0]
    sample_shapes = {key: list(value.shape) for key, value in sample.items()}
    print(json.dumps({"sample_shapes": sample_shapes}, ensure_ascii=True))

    if writer is not None:
        writer.add_text("run/config", json.dumps(vars(args), ensure_ascii=True, indent=2).replace("\n", "  \n"))
        writer.add_text("data/summary", json.dumps(dataset_summary, ensure_ascii=True, indent=2).replace("\n", "  \n"))
        writer.add_text("data/sample_shapes", json.dumps(sample_shapes, ensure_ascii=True, indent=2).replace("\n", "  \n"))


def log_epoch_metrics(writer: SummaryWriter | None, split: str, metrics: dict[str, float], epoch: int) -> None:
    if writer is None:
        return
    for key, value in metrics.items():
        writer.add_scalar(f"{split}/{key}", value, epoch)


def log_parameter_histograms(writer: SummaryWriter | None, model: torch.nn.Module, epoch: int) -> None:
    if writer is None:
        return
    for name, param in model.named_parameters():
        writer.add_histogram(f"params/{name}", param.detach().cpu(), epoch)
        if param.grad is not None:
            writer.add_histogram(f"grads/{name}", param.grad.detach().cpu(), epoch)


def run_epoch(
    model: LSTMBaseline,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
    max_batches: int | None,
    writer: SummaryWriter | None = None,
    epoch: int | None = None,
    global_step: int = 0,
    batch_log_every: int = 0,
) -> tuple[dict[str, float], int]:
    training = optimizer is not None
    model.train(training)
    totals = {
        "loss": 0.0,
        "mse": 0.0,
        "point": 0.0,
        "mag": 0.0,
        "smooth": 0.0,
        "event": 0.0,
        "balance": 0.0,
        "router_entropy": 0.0,
        "grad_norm": 0.0,
    }
    steps = 0
    
    all_pred = []
    all_target = []

    context = torch.enable_grad() if training else torch.no_grad()
    with context:
        for batch_idx, batch in enumerate(loader):
            if max_batches is not None and batch_idx >= max_batches:
                break
            batch = move_batch(batch, device)
            out = model(
                x=batch["x"],
                time_feat=batch["time_feat"],
                gap_feat=batch["gap_feat"],
                kp_feat=batch["kp_feat"],
                station_feat=batch["station_feat"],
            )
            losses = total_loss(out["point"], batch["y"],objective="composite")

            all_pred.append(out["point"].detach().cpu())
            all_target.append(batch["y"].detach().cpu())

            if training:
                optimizer.zero_grad(set_to_none=True)
                losses["loss"].backward()
                grad_norm_raw = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                grad_norm = float(grad_norm_raw.detach().cpu()) if isinstance(grad_norm_raw, torch.Tensor) else float(grad_norm_raw)
                optimizer.step()
                totals["grad_norm"] += grad_norm
                global_step += 1
                if writer is not None and batch_log_every > 0 and global_step % batch_log_every == 0:
                    for key, value in losses.items():
                        writer.add_scalar(f"train_batch/{key}", float(value.detach().cpu()), global_step)
                    writer.add_scalar("train_batch/grad_norm", grad_norm, global_step)
                    writer.add_scalar("train_batch/lr", current_lr(optimizer), global_step)

            for key in totals:
                if key == "grad_norm":
                    continue
                totals[key] += float(losses[key].detach().cpu())
            steps += 1

    metrics = {k: v / max(steps, 1) for k, v in totals.items()}
    if len(all_pred) > 0:
        pred = torch.cat(all_pred, dim=0).numpy()
        target = torch.cat(all_target, dim=0).numpy()

        # 展平成二维
        pred = pred.reshape(-1, pred.shape[-1])
        target = target.reshape(-1, target.shape[-1])

        metrics["r2"] = float(
            r2_score(
                target,
                pred,
                multioutput="uniform_average"
            )
        )

    if not training:
        metrics["grad_norm"] = 0.0
    if writer is not None and epoch is not None:
        log_epoch_metrics(writer, "train" if training else "eval", metrics, epoch)
    return metrics, global_step


def save_checkpoint(
    model: LSTMBaseline,
    optimizer: torch.optim.Optimizer,
    args: argparse.Namespace,
    path: Path,
    val_metrics: dict[str, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "config": vars(args),
            "val_metrics": val_metrics,
        },
        path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an LSTM baseline on chronological geomagnetic station data.")
    parser.add_argument("--csv_path", type=str, default=r"D:\ELE\chronological_kp_dataset")
    parser.add_argument("--cache_path", type=str, default=r"D:\ELE\chronological_kp_dataset\geomf_cache.npz")
    parser.add_argument("--force_cache", action="store_true")
    parser.add_argument("--seq_len", type=int, default=240)
    parser.add_argument("--pred_len", type=int, default=60)
    parser.add_argument("--hidden_dim", type=int, default=256)
    parser.add_argument("--num_layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--learning_rate", type=float, default=1e-3)
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--train_step", type=int, default=240)
    parser.add_argument("--eval_step", type=int, default=60)
    parser.add_argument("--max_train_samples", type=int, default=None)
    parser.add_argument("--max_eval_samples", type=int, default=4096)
    parser.add_argument("--max_train_batches", type=int, default=None)
    parser.add_argument("--max_eval_batches", type=int, default=None)
    parser.add_argument("--num_workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--split_ratios", type=float, nargs=3, default=(0.75, 0.10, 0.15))
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--checkpoint_dir", type=str, default="checkpoints/lstm_baseline")
    parser.add_argument("--log_dir", type=str, default="runs")
    parser.add_argument("--disable_tensorboard", action="store_true")
    parser.add_argument("--tensorboard_batch_log_every", type=int, default=20)
    parser.add_argument("--tensorboard_hist_every", type=int, default=5)
    parser.add_argument("--run_name", type=str, default="lstm_chrono_kp")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    writer = create_tensorboard_writer(args)

    cache_path = prepare_geomag_cache(args.csv_path, args.cache_path, force=args.force_cache)
    print(f"Using cache: {cache_path}")

    cfg = LSTMBaselineConfig(
        seq_len=args.seq_len,
        pred_len=args.pred_len,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
        dropout=args.dropout,
    )

    device = torch.device(args.device)
    train_loader, val_loader, test_loader = build_loaders(args)
    describe_dataset(args, train_loader, val_loader, test_loader, writer)
    model = LSTMBaseline(cfg).to(device)
    total_params, trainable_params = count_parameters(model)
    print(json.dumps({"model_params": {"total": total_params, "trainable": trainable_params}}, ensure_ascii=True))
    if writer is not None:
        writer.add_scalar("meta/total_parameters", total_params, 0)
        writer.add_scalar("meta/trainable_parameters", trainable_params, 0)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))

    best_val = float("inf")
    checkpoint_path = Path(args.checkpoint_dir) / f"{args.run_name}.pt"
    history = []
    global_step = 0

    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()
        train_metrics, global_step = run_epoch(
            model,
            train_loader,
            optimizer,
            device,
            args.max_train_batches,
            writer=writer,
            epoch=epoch,
            global_step=global_step,
            batch_log_every=args.tensorboard_batch_log_every,
        )
        val_metrics, _ = run_epoch(
            model,
            val_loader,
            None,
            device,
            args.max_eval_batches,
        )
        scheduler.step()
        elapsed = time.time() - epoch_start

        record = {
            "epoch": epoch,
            "train": train_metrics,
            "val": val_metrics,
            "lr": scheduler.get_last_lr()[0],
            "seconds": elapsed,
        }
        history.append(record)
        print(json.dumps(record, ensure_ascii=True))

        log_epoch_metrics(writer, "val", val_metrics, epoch)
        if writer is not None:
            writer.add_scalar("meta/lr", current_lr(optimizer), epoch)
            writer.add_scalar("meta/epoch_seconds", elapsed, epoch)
            writer.add_scalar("meta/best_val_loss", min(best_val, val_metrics["loss"]), epoch)

        if val_metrics["loss"] < best_val:
            best_val = val_metrics["loss"]
            save_checkpoint(model, optimizer, args, checkpoint_path, val_metrics)

        if args.tensorboard_hist_every > 0 and epoch % args.tensorboard_hist_every == 0:
            log_parameter_histograms(writer, model, epoch)

    if checkpoint_path.exists():
        state = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(state["model_state"])

    test_metrics, _ = run_epoch(
        model,
        test_loader,
        None,
        device,
        args.max_eval_batches,
    )
    print(json.dumps({"test": test_metrics}, ensure_ascii=True))
    log_epoch_metrics(writer, "test", test_metrics, args.epochs)

    history_path = checkpoint_path.with_suffix(".history.json")
    history_path.write_text(json.dumps(history, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Saved checkpoint to {checkpoint_path}")
    print(f"Saved history to {history_path}")
    if writer is not None:
        writer.flush()
        writer.close()


if __name__ == "__main__":
    main()
