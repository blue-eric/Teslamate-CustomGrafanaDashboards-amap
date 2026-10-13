# 首先感谢作者开发这么好的仪表板，然后我根据hipudding大神的思路，把仪表板改为了高德地图，这样在中国使用更方便。

## 高德地图版说明

本仓库在原版基础上做了以下修改：

- `CurrentChargeView`、`CurrentDriveView`、`CurrentState`、`TrackingDrives` 四个仪表板的地图底图由 OpenStreetMap 改为高德地图。
- 高德地图使用 GCJ-02（火星坐标系），而 TeslaMate 记录的是 WGS-84 坐标，因此轨迹查询会先通过 `wgs84_to_gcj02` 函数做坐标转换，再按 5 秒聚合，避免轨迹偏移。

### 坐标转换函数 `wgs84_to_gcj02`

上述仪表板通过数据库函数 `wgs84_to_gcj02(经度, 纬度)` 把轨迹转换为高德坐标，它与 hipudding 的 TeslaMate 工具（`hipudding/grafana`、`hipudding/teslamate_fix_addrs`）创建的是**同一个函数**，写法和算法完全一致。

- **已经在用 hipudding 的工具**：数据库里已有这个函数，无需任何操作。
- **没有用 hipudding 的工具**：导入仪表板之前，在 TeslaMate 数据库中执行一次 [`scripts/wgs84_to_gcj02.sql`](./scripts/wgs84_to_gcj02.sql)，否则地图面板会报错 `function wgs84_to_gcj02 does not exist`。

以官方 Docker 安装方式为例（数据库服务名为 `database`，用户和库名均为 `teslamate`，请按实际情况修改）：

```bash
docker compose exec -T database psql -U teslamate -d teslamate < ~/Teslamate-CustomGrafanaDashboards-amap/scripts/wgs84_to_gcj02.sql
```

这个脚本只在函数不存在时才创建，**不会覆盖已有的函数**，执行多次也没有影响：已存在时会提示 `wgs84_to_gcj02 already exists, nothing to do`。中国大陆以外的坐标会原样返回。

## 中文版仪表板

`dashboards-zh/` 是中文版仪表板，由脚本根据英文版 `dashboards/` 和翻译表 `i18n/zh-CN.json` 自动生成，**请不要直接修改 `dashboards-zh/` 里的文件**。

中文版和英文版使用不同的 uid、标签和 Grafana 文件夹，可以只装中文版，也可以两套同时安装。

### 安装中文版

在 TeslaMate 的 `docker-compose.yml` 中，grafana 容器的 `volumes` 里加上这两行（如需同时保留英文版，把下文英文说明中的两行也一起加上）：

```yaml
      - ~/Teslamate-CustomGrafanaDashboards-amap/customdashboards-zh.yml:/etc/grafana/provisioning/dashboards/customdashboards-zh.yml
      - ~/Teslamate-CustomGrafanaDashboards-amap/dashboards-zh:/TeslamateCustomDashboardsZh
```

然后重建 Grafana 容器（`docker compose up -d`），Grafana 中会出现"TeslaMate 自定义仪表板"文件夹。别忘了先按上一节确认数据库里有 `wgs84_to_gcj02` 函数。

### 翻译的范围

翻译表分为三个文件：

| 文件 | 内容 | 维护方式 |
| --- | --- | --- |
| `i18n/zh-CN.json` | 标题、说明、表头、图例、筛选项等界面文字，以及 SQL 返回的列名（如 `"Logged"`） | `--update` 自动收集新文字，填写译文即可 |
| `i18n/zh-CN.sql.json` | SQL 里只用于显示的文字片段（如 `'Other'`、月份格式 `'YYYY Month'`），按原样替换 | 手动维护，只放不参与比较和关联的显示文字 |
| `i18n/zh-CN.values.json` | 数据库原始值的显示文字（如车辆状态 online/asleep） | 手动维护 |

说明：

- SQL 返回的列名不修改 SQL，而是通过 Grafana 的"显示名称"覆盖来翻译，查询本身保持不变。
- 带空格、大写或符号的列名（如 `"Power [kW]"`）会被自动收集；像 `speed` 这种标识符形式的列名需要手动加到 `i18n/zh-CN.json` 才会翻译。
- 以下文字由 Grafana 自身生成，仪表板无法翻译：时长格式（如 "2 hours, 35 minutes"）、图例统计名（Max/Min/Mean/Last）、开关值（On/Off）、表格表头 Name/Value/Percent 等。
- 地址、地理围栏名称、充电运营商等是你的数据，保持原样。

### 与原作者仓库同步

原作者更新或新增面板后，按以下步骤同步：

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

- 如果合并时出现冲突，通常是原作者修改了已改为高德地图的 4 个地图面板，需要手动保留高德底图和 `wgs84_to_gcj02` 坐标转换后再继续。
- 翻译中的 `$变量`、`${变量}` 必须原样保留（可以写成 `${变量:text}` 来显示选项文字），否则脚本会给出警告并保留英文。
- 原作者删除的文字会留在翻译表中，可用 `python3 scripts/build_i18n.py --prune` 清理。
- 如果原作者改动了 `i18n/zh-CN.sql.json` 或 `i18n/zh-CN.values.json` 中引用的 SQL，脚本会提示"no longer found"，需要对照新的 SQL 更新这两个文件。
- 新增面板如果用正则选择字段（如 `/^Added$/`），脚本会自动同步改名；更复杂的正则会保留英文列名，以免面板显示 No data。

# TeslaMate Custom Grafana Dashboards

### Last release: [v2026.8.14](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards/releases/)

<!-- PROJECT SHIELDS -->
<!--
*** I'm using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->
[![Stargazers][stars-shield]][stars-url][![Contributors][contributors-shield]][contributors-url][![Forks][forks-shield]][forks-url][![Issues][issues-shield]][issues-url][![Discussions][discussions-shield]][discussions-url][![MIT License][license-shield]][license-url]

This is a project with **Custom Grafana Dashboards**, created especially to work with a **Teslamate installation**. So the main requirement for these dashboards to work, is to have a **[Teslamate](https://docs.teslamate.org/)** running instance.

## TeslaMate

**[Teslamate](https://docs.teslamate.org/)** is a powerful, self-hosted data logger for your Tesla.

- Written in **[Elixir](https://elixir-lang.org/)**
- Data is stored in a **Postgres** database
- Visualization and data analysis with **Grafana**
- Vehicle data is published to a local **MQTT** Broker

___

## How to Auto-import these Custom Dashboards

In order to auto-import all the dashboard files from this repository, considering that your are using the official  [Teslamate Docker install](https://docs.teslamate.org/docs/installation/docker) documentation guide, proceed as follows.

**Note:** If you are using Teslamate without Docker you may skip these section and proceed to import manually.

- The following command will clone the source files from this repository. This should be run in an appropriate directory within which you would like to keep it. You should also record this path and provide it later in the following steps. To keep it easy, you may run this your home path (~/) or modify it accordingly.

```bash
git clone https://github.com/blue-eric/Teslamate-CustomGrafanaDashboards-amap.git
```

- Edit your Teslamate "docker-compose.yml" file and add these two new lines at the end of the "volumes" section of the grafana container

```yaml
services:
  ...
  ...
  grafana:
    ...
    ...
    volumes:
      - teslamate-grafana-data:/var/lib/grafana
      - ~/Teslamate-CustomGrafanaDashboards-amap/customdashboards.yml:/etc/grafana/provisioning/dashboards/customdashboards.yml
      - ~/Teslamate-CustomGrafanaDashboards-amap/dashboards:/TeslamateCustomDashboards
```

- Save your file and then **recreate** Grafana container (docker-compose up -d)
- Browse the Grafana Dashboards from the Web and you should have a new "TeslaMate Custom Dashboards" folder

## Using other path for repository

Attention! On some VPS from certain providers like Google GCC, the user running docker engine is not the current user so it's home folder is different, or maybe you just want to use a specific folder for your data. If this is the case, it's better to use the **full path** of the repository where you cloned it, instead of using the home path of the current user (~/). So, be sure to modify the path of the volumes section accordingly, as the sample given below:

```yaml
services:
  ...
  ...
  grafana:
    ...
    ...
    volumes:
      - teslamate-grafana-data:/var/lib/grafana
      - /some/path/Teslamate-CustomGrafanaDashboards-amap/customdashboards.yml:/etc/grafana/provisioning/dashboards/customdashboards.yml
      - /some/path/Teslamate-CustomGrafanaDashboards-amap/dashboards:/TeslamateCustomDashboards
```

## How to update the Dashboards

If you want to be sure that you are using the latest version of the Dashboards:

- Pull again from the repository

```bash
git -C ~/Teslamate-CustomGrafanaDashboards-amap pull
```

- Then **restart** Grafana container

```bash
docker compose restart grafana  
```

Or (if you are using a previous docker version)

```bash
docker-compose restart grafana  
```

## How to use these Custom Dashboards

In order to use these dashboards, once imported, you may want to go to the Grafana "Browse" option (from the left vertical bar), from there you will see a new folder with the imported dashboards.

![Browse](./screenshots/help/browseoption.png) ![Custom Dashboards](./screenshots/help/customdasboardfolder.png)

This Custom Dashboards have a special label so they don't get mixed up with the Teslamate defaults dashboards to distinguish easier and group together. When you are in a Custom Dashboard you will see in the upper right corner, a drop-down button from  you may access the rest dashboards as well.

![DropDown](./screenshots/help/dropdownbutton.png)
___

## How to manually import these custom dashboards

The following steps let you import the JSON files into your setup if you don't want to auto-import them:

- On Grafana (from Teslamate instance), Browse Dashboards then Import...
- Upload JSON file or import via panel json by pasting the raw content of te JSON file.
- On the next screen you may name the dashboard as you wish or accept the suggested one.
- Try to keep UID as it is, because it could be linked inside the dashboard and to avoid duplicates UIDs.
- Finally, press the "Import" button

## Tips on Dashboards

Have in mind that each dashboard may have an "Information" icon (as shown in the following image). If you point on it, you'll have aditional information on the current panel. Try to check it while you are browsing or analyzing your data.

![InfoIcon](./screenshots/help/infoicon.png)
___

## Screenshots

### [Amortization Tracker](./dashboards/AmortizationTracker.json)

This dashboard aims to show the depreciation value of the car over time and its journey.
Depreciating a car by its mileage can be done using various methods. A common approach is to use a depreciation rate per mile or to create a depreciation curve based on data. On the other hand, the depreciation of a car due to age can vary depending on several factors such as the make, model, overall condition of the vehicle, and demand in the market. Here you can put your costs, rates and other variable values to have and idea of the depreciated car value and fuel savings.

![Amortization Tracker](./screenshots/AmortizationTracker.png)

### [Battery Health](./dashboards/BatteryHealth.json)

This dashboard has been already migrated (given) to the core dashboards of Teslamate and will continue developing directly there with the collaboration of all the enthusiasts in the community. You will find it there with the same name **Battery Health**.

![Battery Health](./screenshots/BatteryHealth.png)

### [Browse Charges](./dashboards/BrowseCharges.json)

This dashboard has been already migrated (given) to the core dashboards of Teslamate and will continue developing directly there with the collaboration of all the enthusiasts in the community. You will find it there with the name **Charges**.

![Browse Charges](./screenshots/BrowseCharges.png)

### [Charging Costs Stats](./dashboards/ChargingCostsStats.json)

This dashboard is meant to have a look of all the charges in a given period (last 10 years by default).
You can see the distance driven, number of charges, total charging cost, etc., both in summary or in
separated lists.

You can expand/collapse the rows as needed.

From the Monthly Stats row, you will have a table with links to other Teslamate Dashboards to have a look on a specific period, charge or trip.

![Charging Costs Stats](./screenshots/ChargingCostsStats.png)

### [Charging Curve Stats](./dashboards/ChargingCurveStats.json)

This dashboard is meant to have a look of the charging curve sessions on Tesla Supercharges or other Fast Charging Station. Also, you can see number of fast charging sessions you've done on each type of chargers and the count of max power (kW) reached on a session as shown in the following example.

![Charging Curve Stats](./screenshots/ChargingCurveStats.png)

### [Continuous Trips](./dashboards/ContinuousTrips.json)

This dashboard has a table with all the trips you've made between charges sesions, so you can browse the longest or shortest mileage you travel.

You may also take a look to a specific trip from the initial charge session (before the trip) to the end of the of the charge session (after the trip), through the link in the first column that will take you to the TeslaMate Trips dashboard.

![Continuous Trips](./screenshots/ContinuousTrips.png)

### [Current Charge View](./dashboards/CurrentChargeView.json)

Load this dashboard to while you are in a charging sesion. When you open this dashboard it will show the last 15 minutes, but you should click the "Current Charge" button at the top right corner, to enter in Kiosk mode:

- If you are charging, you will see the information from the start time of the current charge session until now and it will refesh automatically every 30 seconds.
- If you are just browsing (not charging) you will see the information of the last charge session.  

![Current Charge View](./screenshots/CurrentChargeView.png)

### [Current Drive View](./dashboards/CurrentDriveView.json)

This is a special dashboard to load while driving. When you open this dashboard it will show the last 15 minutes, but you should click the "Current Drive" button at the top right corner, to enter in Kiosk mode:

- If you are driving, you will see the information from the start time of the current drive until now and it will refesh automatically every 30 seconds.
- If you are just browsing (not driving) you will see the information of the last drive.  

![Current Drive View](./screenshots/CurrentDriveView.png)

### [Current State](./dashboards/CurrentState.json)

This dasboard is just to see the current state of the car with the last data recorded by TeslaMate.

Additionally, you can see the states stats of the selected period.

![Current State](./screenshots/CurrentState.png)

### [Database Information](./dashboards/CurrentState.json)

This dashboard has been already migrated (given) to the core dashboards of Teslamate and will continue developing directly there with the collaboration of all the enthusiasts in the community. You will find it there with the name **Database Information**.

![Database Information](./screenshots/DatabaseInfo.png)

### [DC Charging Curves By Carrier](./dashboards/DC_ChargingCurvesByCarrier.json)

This dasboard is browse your DC charge sessions by charger carriers.

It's important that you have Geo-Fences added related with the name of the carrier
you have recharged your car, or you may want to edit periodically the **name** field of the **addresses** table, so that it contains its name.

For example, if **Teslamate** geolocates the name as *"Esso Purley Way"* you may modify it to *"Esso Purley Way - IONITY"* or *"IONITY Esso Purley Way"*, then you can filter using the filter textbox **IONITY** to show all the charging curves of all charging sessions at that carrier.

![DC Charging Curves By Carrier](./screenshots/DC_ChargingCurvesByCarrier.png)

### [Incomplete Data](./dashboards/IncompleteData.json)

With this dashboard you may find your incomplete drives or charges that have been interrupted by the connection or any other issue. So you may follow the official guide to fix it.

![Incomplete Data](./screenshots/IncompleteData.png)

### [Range Degradation](./dashboards/RangeDegradation.json)

In this dashboard you may analyze your mileage and the range degradation by a selected period.

So you may have an idea of how much of range is lost as well as if there were any failure in Teslamate logging your data.  

![Range Degradation](./screenshots/RangeDegradation.png)

### [Mileage Stats](./dashboards/MileageStats.json)

With this dashboard you may analyze your mileage and number of drives by year, month, week or day.

The dashboard shows a table with the selected period, time driven, distance, number of drives and efficiency then a bar chart to have a better look for comparison.  

![Mileage Stats](./screenshots/MileageStats.png)

### [Speed Rates](./dashboards/SpeedRates.json)

In this dashboard you can browse the speed rates by segments, based on terrain type: Flat, Uphill or Downhill. This way you can see the average consumtion by speed and its average distance.
Likewise, you can see the Top speeds you reached and how long it lasted.

![Speed Rates](./screenshots/SpeedRates.png)

### [Speed & Temperature](./dashboards/SpeedTemperature.json)

In this dashboard you can browse and analyse the car consumption by temperature in short and long stretches. This way you can see the average consumption depending on the temperature to better understand the efficiency of the car in cold or hot climates.

![Speed Temperature](./screenshots/SpeedTemperature.png)

### [Tracking Drives](./dashboards/TrackingDrives.json)

This dashboard is meant to analyze a drive based on a date you select, then you can pass the pointer over the lines in graph
to see data details and a blue point in the map tranking the route. With this option you can analyze a specific point location in the map,
to see the speed, power, SOC, elevation and if battery heater was on.

Be aware that the drive you select in the dropdown list from the top could be outside the time range of the Timeline graph,
if its the case you have to click on the "Zoom to data" button on the graph in order to update it.

Tip: On Grafana you can press "h" to get a keyboard shortcuts if you want to change the current Zoom out time range or use the mouse to select/change the time range.

![Tracking Drives](./screenshots/TrackingDrives.gif)

## Contributing

The following dashboards, queries and design are the result of many tests and hours of work.
Feel free to take them for your own personal use.

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are greatly appreciated.

If you are able to contibute or improve this project, please fork the repository and create a pull request. I'll really apreciate any enhancement or suggestion. Don't forget to give the project a star! Thanks again!

### Steps to create a pull request

1. Fork the Project
2. Change to the "develop" Branch (`git checkout develop`)
3. Create your Feature Branch (`git checkout -b feature/NewFeature`)
4. Commit your Changes (`git commit -m 'Add some NewFeature'`)
5. Push to the Branch (`git push origin feature/NewFeature`)
6. Open a Pull Request

Do not take the dashboards much less upload or merge them to other repositories as if the original idea were yours, nor do you share it on social media without mentioning the author. Please, **respect the ingenuity and work of others**. Enjoy!

## Donations

|     |     |
| --- | --- |
| If you like my work and want to support me, buying me a coffee would be greatly appreciated! Your support helps me to keep creating and improving these dashboards. Thank you! | [![Paypal Donate](https://img.shields.io/badge/Donate-PayPal-ff69b4.svg)](https://www.paypal.com/donate/?business=MAWY99TACEXSU&no_recurring=0&currency_code=EUR) |
| Other way to support me is to use [my referral link](https://ts.la/juancarlos32618) to purchase a Tesla product and get Credits you can redeem for exclusive awards like Supercharging miles, merchandise, and accessories. | [![Tesla referral link](./screenshots/help/tesla.png)](https://ts.la/juancarlos32618) |
|     |     |

## Credits

- Author: [Juan Carlos Heredia](https://infoinnova.net/contacto/)
- Based on/forked from [Adrian Kumpf](https://github.com/adriankumpf/teslamate) original code, with improvement of custom Grafana Dashboards (see [contributions history](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards/graphs/contributors)).

## License

Licensed under the [MIT license][license-url].

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/jheredianet/Teslamate-CustomGrafanaDashboards.svg?style=for-the-badge
[contributors-url]: https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/jheredianet/Teslamate-CustomGrafanaDashboards.svg?style=for-the-badge
[forks-url]: https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards/network/members
[stars-shield]: https://img.shields.io/github/stars/jheredianet/Teslamate-CustomGrafanaDashboards.svg?style=for-the-badge
[stars-url]: https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards/stargazers
[issues-shield]: https://img.shields.io/github/issues/jheredianet/Teslamate-CustomGrafanaDashboards.svg?style=for-the-badge
[issues-url]: https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards/issues
[discussions-shield]: https://img.shields.io/github/discussions/jheredianet/Teslamate-CustomGrafanaDashboards.svg?style=for-the-badge
[discussions-url]: https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards/discussions
[license-shield]: https://img.shields.io/github/license/jheredianet/Teslamate-CustomGrafanaDashboards.svg?style=for-the-badge
[license-url]: ./LICENSE
