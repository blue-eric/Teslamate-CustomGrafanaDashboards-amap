# TeslaMate 自定义仪表板（高德地图 + 中文版）

为国内 TeslaMate 用户准备的一套 Grafana 自定义仪表板：

- **高德地图**：地图面板使用高德底图，轨迹自动从 WGS-84 转换为 GCJ-02（火星坐标），不再偏移。
- **中文界面**：标题、表头、图例、筛选项、提示文字等全部汉化，车辆状态等数据值也显示为中文。
- **适配国内使用习惯**：
  - 充电曲线统计能识别中文命名的超充站（如"特斯拉超级充电站""超充"）；
  - 充电费用统计可把多个地理围栏合并为"家""公司"统计（名称含 家/住、公司/单位/办公 等）；
  - 修复了"当前状态"中预估续航显示 N/A 的问题。
- **持续跟进原作者更新**：原作者新增或修改仪表板后，本仓库会同步并补上中文翻译。

## 仪表板一览

| 仪表板 | 说明 |
| --- | --- |
| 当前状态 | 车辆最新状态、位置（高德地图）、电量与预估续航，以及所选时段的状态统计 |
| 当前行程 | 开车时使用：实时显示本次行程的轨迹（高德地图）、车速、功率等，每 30 秒刷新；不在行驶时显示上一次行程 |
| 当前充电 | 充电时使用：实时显示本次充电的位置（高德地图）、功率、电压电流等，每 30 秒刷新；不在充电时显示上一次充电 |
| 行程追踪 | 选择一次行程，鼠标划过曲线时在高德地图上同步标出位置，查看该点的车速、功率、电量、海拔等 |
| 连续行程 | 列出两次充电之间的全部行程，可跳转到 TeslaMate 的行程仪表板查看详情 |
| 充电费用统计 | 指定时段内的行驶里程、充电次数、充电费用等汇总与明细，主要充电地点按"家 / 公司 / 其他"分组 |
| 充电曲线统计 | 特斯拉超充和其他快充的充电曲线、各类充电桩的充电次数及最大功率分布 |
| 按运营商统计直流充电曲线 | 按充电运营商筛选直流充电曲线（需要地理围栏或地址名称中包含运营商名） |
| 里程统计 | 按年 / 月 / 周 / 日统计里程、驾驶时间、行程次数和能耗 |
| 续航衰减 | 按时段分析里程和续航衰减，也能看出 TeslaMate 是否漏记数据 |
| 车速分析 | 按平路 / 上坡 / 下坡和车速区间统计平均能耗与距离，以及最高车速记录 |
| 车速与温度 | 不同气温下的能耗，了解车辆在严寒或酷暑时的效率 |
| 购车回本追踪 | 填入购车成本等参数，估算车辆折旧和相比燃油车节省的费用 |
| 不完整数据 | 找出因断网等原因中断的行程和充电记录，便于按官方指南修复 |

## 安装

前提：已按 [TeslaMate 官方 Docker 方式](https://docs.teslamate.org/docs/installation/docker) 安装并正常运行。

### 1. 下载本仓库

在服务器上选一个目录（下面以 `~/` 为例）执行：

```bash
git clone https://github.com/blue-eric/Teslamate-CustomGrafanaDashboards-amap.git
```

### 2. 挂载到 Grafana

编辑 TeslaMate 的 `docker-compose.yml`，在 grafana 服务的 `volumes` 末尾加上两行：

```yaml
services:
  grafana:
    ...
    volumes:
      - teslamate-grafana-data:/var/lib/grafana
      - ~/Teslamate-CustomGrafanaDashboards-amap/customdashboards-zh.yml:/etc/grafana/provisioning/dashboards/customdashboards-zh.yml
      - ~/Teslamate-CustomGrafanaDashboards-amap/dashboards-zh:/TeslamateCustomDashboardsZh
```

- 群晖等 NAS、或运行 Docker 的用户不是当前用户时，请把 `~/` 换成**完整路径**，例如 `/volume1/docker/Teslamate-CustomGrafanaDashboards-amap/...`。
- 如果还想要英文版（同样是高德地图），再加两行；中英文版使用不同的文件夹和 uid，可以同时安装：

```yaml
      - ~/Teslamate-CustomGrafanaDashboards-amap/customdashboards.yml:/etc/grafana/provisioning/dashboards/customdashboards.yml
      - ~/Teslamate-CustomGrafanaDashboards-amap/dashboards:/TeslamateCustomDashboards
```

### 3. 准备坐标转换函数

地图面板需要 TeslaMate 数据库里有 `wgs84_to_gcj02` 函数：

- **Grafana 使用 [`hipudding/grafana`](https://hub.docker.com/r/hipudding/grafana) 镜像**（推荐，TeslaMate 自带仪表板也是高德地图）：镜像每次启动都会自动创建该函数，跳过这一步。
- **Grafana 使用官方 `teslamate/grafana` 等其他镜像**：执行一次下面的命令（数据库服务名、用户名、库名请按实际修改）：

```bash
docker compose exec -T database psql -U teslamate -d teslamate < ~/Teslamate-CustomGrafanaDashboards-amap/scripts/wgs84_to_gcj02.sql
```

该脚本创建的函数与 `hipudding/grafana` 镜像中的完全相同，以后更换镜像也不会冲突，重复执行没有影响。如果数据库里已有一个写法不同、或正被其他程序使用的同名函数，脚本会中止且不做任何修改。

### 4. 启动

```bash
docker compose up -d
```

打开 Grafana，在"仪表板"中会出现 **TeslaMate 自定义仪表板** 文件夹。进入任意一个仪表板后，右上角的下拉按钮可以在各仪表板之间切换。

## 更新

```bash
git -C ~/Teslamate-CustomGrafanaDashboards-amap pull
docker compose restart grafana
```

## 常见问题

- **地图面板报错 `function wgs84_to_gcj02 does not exist`**：没有完成安装第 3 步。
- **轨迹偏移几百米**：使用的不是本仓库的仪表板，或仪表板被手动改过，重新 `git pull` 并重启 Grafana。
- **部分文字仍是英文**：时长格式（如 "2 hours, 35 minutes"）、图例统计名（Max / Min / Mean）、开关值（On / Off）等由 Grafana 自身生成，仪表板无法翻译；地址、地理围栏名称、充电运营商等是你自己的数据，保持原样。

## 维护说明

以下内容供本仓库维护使用，普通用户无需关注。

`dashboards-zh/` 由脚本根据英文版 `dashboards/` 和翻译表自动生成，**不要直接修改 `dashboards-zh/` 里的文件**。

| 文件 | 内容 | 维护方式 |
| --- | --- | --- |
| `i18n/zh-CN.json` | 标题、说明、表头、图例、筛选项等界面文字，以及 SQL 返回的列名（如 `"Logged"`） | `--update` 自动收集新文字，填写译文即可 |
| `i18n/zh-CN.sql.json` | SQL 里只用于显示的文字片段（如 `'Other'`、月份格式 `'YYYY Month'`），按原样替换 | 手动维护，只放不参与比较和关联的显示文字 |
| `i18n/zh-CN.values.json` | 数据库原始值的显示文字（如车辆状态 online / asleep） | 手动维护 |

同步原作者的更新：

```bash
# 1. 合并原作者的最新代码，并把新出现的英文文字加入翻译表
bash scripts/sync_upstream.sh

# 2. 打开 i18n/zh-CN.json，填写值为 "" 的条目（没填的会暂时显示英文）

# 3. 重新生成中文版并检查
python3 scripts/build_i18n.py
python3 scripts/build_i18n.py --check

# 4. 提交
git add -A && git commit -m "Sync upstream and update Chinese translation"
```

注意事项：

- 本 README 是独立编写的，同步时始终保留本仓库的版本（由 `.gitattributes` 和同步脚本自动处理）。
- 合并冲突通常出现在已改为高德地图的 4 个地图仪表板（当前状态、当前行程、当前充电、行程追踪），需要手动保留高德底图和 `wgs84_to_gcj02` 坐标转换。
- SQL 返回的列名不修改 SQL，而是通过 Grafana 的"显示名称"覆盖来翻译；带空格、大写或符号的列名（如 `"Power [kW]"`）会被自动收集，像 `speed` 这种标识符形式的列名需要手动加到 `i18n/zh-CN.json`。
- 翻译中的 `$变量`、`${变量}` 必须原样保留（可以写成 `${变量:text}` 显示选项文字），否则脚本会警告并保留英文。
- 原作者删除的文字会留在翻译表中，可用 `python3 scripts/build_i18n.py --prune` 清理。
- 脚本提示 "no longer found" 时，说明原作者改了 `zh-CN.sql.json` 或 `zh-CN.values.json` 引用的 SQL，需要对照新 SQL 更新这两个文件。
- 新增面板如果用正则选择字段（如 `/^Added$/`），脚本会自动同步改名；更复杂的正则会保留英文列名，以免面板显示 No data。

## 致谢

- **[Juan Carlos Heredia（jheredianet）](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards)**：本仓库的全部仪表板设计和查询均来自他的 TeslaMate Custom Grafana Dashboards 项目，本仓库只在其基础上做了高德地图适配和汉化。喜欢这些仪表板的话，欢迎去原项目点个 Star 或[支持作者](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards#donations)。
- **[hipudding](https://github.com/hipudding/teslamate)**：高德地图方案和 `wgs84_to_gcj02` 坐标转换函数来自他的 TeslaMate 高德地图版及 `hipudding/grafana` 镜像。
- [TeslaMate](https://github.com/teslamate-org/teslamate)：优秀的自托管特斯拉数据记录工具。

## 许可证

[MIT](./LICENSE)，与原项目相同。
