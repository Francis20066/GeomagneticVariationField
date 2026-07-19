# GeomagneticVariationField

GeomagneticVariationField 是一个面向地磁场计算与地磁变化分析的项目。当前核心目标是把主磁场与 Swarm 外场模型从零散 Python 环境中抽取出来，封装为一个统一的 C++17 高速核心，并通过 `pybind11` 暴露为 Python 原生扩展模块 `magerr_native`。

当前版本已经内置：

- WMM2025 主磁场模型
- Swarm MMA 2C/2F 外场模型资源
- C++17 native 求值核心
- Python 扩展模块 `magerr_native`
- 基础批量查询接口
- wheel 构建配置

> 说明：本项目使用的是 `pybind11`。如果需求中提到 `pybind3`，这里按“面向 Python 3 的 pybind 模块”理解。

## 项目结构

```text
.
├── pyproject.toml                  # Python wheel 构建配置
├── src/
│   ├── CMakeLists.txt              # C++/pybind11 构建入口
│   ├── bindings/                   # Python 扩展绑定
│   ├── cpp/                        # C++ 实现
│   ├── include/                    # C++ public headers
│   ├── resources/                  # 运行时模型资源
│   ├── third_party/                # 内置第三方模型/公式代码
│   └── tools/                      # 开发期资源转换工具
├── tests/                          # native module 测试
├── scripts/                        # 数据处理与实验脚本
├── docs/                           # 项目说明文档
└── data/                           # 本地数据目录，默认不纳入 Git
```

## 已实现能力

### WMM2025 主磁场

项目已内置 NOAA WMM2025 所需的 C 源码与 `WMM.COF` 系数文件。`Wmm2025Provider` 初始化时加载系数，查询时直接在 C++ 中完成主磁场计算，不需要额外安装 `wmm2025` Python 包。

输出字段包括：

- `north`：北向分量，单位 nT
- `east`：东向分量，单位 nT
- `down`：下向分量，单位 nT
- `total`：总场强，单位 nT
- `declination` / `decl`：磁偏角，单位 degree
- `inclination` / `incl`：磁倾角，单位 degree

### Swarm MMA 外场

项目已支持 Swarm MMA 2C/2F 外场模型。原始 CDF 产品通过开发期工具转换为 `.magerr` 运行时资源，Python 用户运行时不需要安装 `geoist` 或 `spacepy`。

当前默认返回：

- `primary`：外源主场分量
- `secondary`：感应次级场分量
- `total`：`primary + secondary`

第一版只覆盖 MMA 2C/2F；MIO 模型尚未纳入 native runtime。

## 构建

### 构建 C++ core

```powershell
cmake -S src -B outputs\build-magerr-core -G "MinGW Makefiles" `
  -DMAGERR_BUILD_PYTHON=OFF `
  -DMAGERR_USE_BUNDLED_WMM=ON

cmake --build outputs\build-magerr-core
```

### 构建 Python 扩展

需要安装构建依赖：

```powershell
python -m pip install pybind11 scikit-build-core
```

然后构建：

```powershell
$pybind = python -c "import pybind11; print(pybind11.get_cmake_dir())"
$py = python -c "import sys; print(sys.executable)"

cmake -S src -B outputs\build-magerr-python -G "MinGW Makefiles" `
  -DMAGERR_BUILD_PYTHON=ON `
  -DMAGERR_USE_BUNDLED_WMM=ON `
  -Dpybind11_DIR="$pybind" `
  -DPython_EXECUTABLE="$py"

cmake --build outputs\build-magerr-python
```

### 构建 wheel

```powershell
$env:CMAKE_GENERATOR = "MinGW Makefiles"
python -m pip wheel . -w outputs\wheels --no-deps --no-build-isolation
```

生成的 wheel 会携带 `resources/` 下的 WMM2025 与 Swarm MMA 模型资源。

## Python 使用示例

如果直接从 CMake 构建目录导入：

```python
import os
import sys

os.add_dll_directory(r"C:\Python314")
os.add_dll_directory(r"C:\Tools\mingw64\bin")
sys.path.insert(0, r"outputs\build-magerr-python")

import magerr_native as magerr
```

查询 WMM2025 主磁场：

```python
field = magerr.wmm_main_field(
    latitude=19.03,
    longitude=109.83,
    altitude_km=0.5,
    time_utc="2025-02-04T00:00:00Z",
)

print(field)
```

查询 Swarm MMA 外场：

```python
external = magerr.swarm_mma_field(
    latitude=19.03,
    longitude=109.83,
    altitude_km=0.5,
    time_utc="2021-02-04T00:00:00Z",
    component="total",
)

print(external)
```

统一查询主场、外场与总场：

```python
result = magerr.field_at(
    latitude=19.03,
    longitude=109.83,
    altitude_km=0.5,
    time_utc="2021-02-04T00:00:00Z",
)

print(result["main"])
print(result["swarm"]["total"])
print(result["total"])
```

时间序列查询：

```python
series = magerr.get_variation_series(
    latitude=19.03,
    longitude=109.83,
    altitude_km=0.5,
    start_time="2021-02-04T00:00:00Z",
    end_time="2021-02-04T00:10:00Z",
    step_seconds=60,
)

print(len(series))
```

批量查询：

```python
batch = magerr.field_at_batch(
    latitudes=[19.03, 20.0],
    longitudes=[109.83, 110.0],
    altitude_km=[0.5, 0.5],
    time_utc=[
        "2021-02-04T00:00:00Z",
        "2021-02-04T00:01:00Z",
    ],
)

print(batch)
```

## 资源转换

Swarm MMA 原始 CDF 产品不在运行时读取。开发期可使用以下工具把 CDF 转换成项目自有资源格式：

```powershell
$env:HOME = (Resolve-Path ".spacepy_home").Path

C:\Users\METEO\miniconda3\envs\swarmfield\python.exe src\tools\convert_swarm_mma.py `
  --mma-2c F:\Data\MagErr\geoist\geoist\model\magmod\data\SW_OPER_MMA_SHA_2C_20131125T000000_20181231T235959_0501.cdf `
  --mma-2f F:\Data\MagErr\geoist\geoist\model\magmod\data\SW_OPER_MMA_SHA_2F_20210101T000000_20211102T223000_0108.cdf `
  --out-dir src\resources\swarm_mma
```

转换后的资源文件：

- `src/resources/swarm_mma/mma_2c.magerr`
- `src/resources/swarm_mma/mma_2f.magerr`

## 测试

从 CMake 构建目录运行测试：

```powershell
$env:MAGERR_NATIVE_PATH = "outputs\build-magerr-python"
$env:MAGERR_DLL_DIRS = "C:\Python314;C:\Tools\mingw64\bin;C:\texlive\2026\bin\windows"

python -m unittest tests.test_native_module
```

当前测试覆盖：

- `magerr_native` 导入
- WMM2025 主磁场冒烟测试
- Swarm MMA 外场冒烟测试
- 统一 series 查询
- 批量查询
- 可选的 `wmm2025` Python reference 对齐测试

如果当前 Python 环境没有安装 `wmm2025`，reference 对齐测试会自动跳过。

## 当前限制

- Swarm 第一版只支持 MMA 2C/2F，不包含 MIO。
- MMA 资源有效期受原始 Swarm 产品限制，超出有效期会返回缺失或抛出范围错误。
- Windows 下使用 MinGW 构建的 `.pyd` 可能需要显式配置 DLL 搜索路径。
- 目前批量接口返回 Python list/dict；后续可以增加 NumPy array 输出以进一步减少 Python 侧开销。

## 提交规范

本仓库提交信息遵循：

```text
type(scope) : subject
```

示例：

```text
feat(wmm) : 内置WMM2025主场模型
feat(swarm) : 添加MMA资源转换与求值
test(native) : 增加模块冒烟测试
docs(readme) : 添加中文项目说明
```
