import pandas as pd
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# 示例：地磁台站
df = pd.DataFrame({
    "code": [
        "VAL", "STT", "SFS", "HAD", "SPT", "ESK", "EBR", "DOU",
        "MAB", "BFO", "WNG", "FUR", "BFE", "NGK", "AQU", "BDV",
        "DUR", "WIC", "LON", "NCK", "THY", "HRB", "HLP", "GCK",
        "BEL", "LVV", "PEG", "PAG", "SUA", "ISK", "IZN", "KIV"
    ],
    "name": [
        "Valentia", "San Teotonio", "San Fernando", "Hartland",
        "San Pablo-Toledo", "Eskdalemuir", "Ebro", "Dourbes",
        "Manhay", "Black Forest", "Wingst", "Furstenfeldbruck",
        "Brorfelde", "Niemegk", "L'Aquila", "Budkov",
        "Duronia", "Conrad Observatory", "Lonjsko Polje", "Nagycenk",
        "Tihany", "Hurbanovo", "Hel", "Grocka",
        "Belsk", "Lviv", "Pedeli", "Panagjurishte",
        "Surlari", "Istanbul-Kandilli", "Iznik", "Kiev"
    ],
    "lat": [
        51.9330, 37.5467, 36.6670, 51.0000,
        39.5500, 55.3140, 40.8200, 50.1000,
        50.2980, 48.3310, 53.7430, 48.1700,
        55.6250, 52.0700, 42.3800, 49.0800,
        41.6500, 47.9305, 45.4081, 47.6300,
        46.9000, 47.8730, 54.6035, 44.6330,
        51.8360, 49.9000, 38.0800, 42.5150,
        44.6800, 41.0630, 40.5000, 50.7170
    ],
    "lon": [
        -10.2500, -8.7277, -5.9450, -4.4800,
        -4.3500, -3.2060, 0.4930, 4.6000,
        5.6820, 8.3250, 9.0730, 11.2800,
        11.6720, 12.6800, 13.3200, 14.0200,
        14.4700, 15.8657, 16.6592, 16.7200,
        17.8900, 18.1900, 18.8107, 20.7670,
        20.7890, 23.7500, 23.9300, 24.1770,
        26.2500, 29.0620, 29.7200, 30.3000
    ],
})
# PlateCarree 可以理解成普通经纬度坐标系
proj = ccrs.PlateCarree()

fig = plt.figure(figsize=(12, 6))
ax = plt.axes(projection=proj)

# 世界范围
ax.set_global()

# 底图要素
ax.add_feature(cfeature.LAND, linewidth=0.3)
ax.add_feature(cfeature.OCEAN)
ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
ax.add_feature(cfeature.BORDERS, linewidth=0.4)

# 网格线
ax.gridlines(draw_labels=True, linewidth=0.3, alpha=0.5)

# 画点：注意 x 是经度 lon，y 是纬度 lat
ax.scatter(
    df["lon"],
    df["lat"],
    s=35,
    transform=ccrs.PlateCarree(),
    zorder=5
)

# 标注台站缩写
for _, row in df.iterrows():
    ax.text(
        row["lon"] + 1,
        row["lat"] + 1,
        row["code"],
        fontsize=8,
        transform=ccrs.PlateCarree()
    )

plt.title("Geomagnetic Stations")
plt.show()