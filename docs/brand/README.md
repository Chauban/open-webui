# RightWrite 品牌视觉规范

本目录与 `static/brand/rightwrite/` 是项目 VI 的维护入口。2026-11-10 从工作区外层 `VI/RightWrite-logo/` 导入正式交付素材；原始交付包留在外层备份，后续开发以仓库内版本为准。未重复导入 ZIP 和外层同名副本。

- [可视化品牌规范](RightWrite-品牌规范.html)：配色、字标、字体、留白和错误用法。浏览器打开可查看；示例图已指向仓库内素材，规范展示页的在线字体需要网络。
- [SVG 素材](../../static/brand/rightwrite/svg/)：主标志、横版与竖版字标、反白版本、App 图标。字标文字已转曲，直接使用，无需字体文件。
- [PNG 素材](../../static/brand/rightwrite/png/)：透明底导出、App 图标和多尺寸 favicon。
- [favicon.ico](../../static/brand/rightwrite/favicon.ico)：多尺寸网站图标。

## 色彩与字体

| 名称 | 色值 | 用途 |
| --- | --- | --- |
| 墨蓝 Ink | `#20406A` | 主文字、笔画与主要操作 |
| 深墨 Deep | `#15314E` | 墨色渐变深端 |
| 珊瑚 Coral | `#FF6A45` | Write 字标、强调与图标背景 |
| 浅珊瑚 | `#FFB199` | 深色背景强调 |
| 纸 Paper | `#F7F3EA` | 页面背景、反白文字 |

字标为 EB Garamond（Right Regular、Write SemiBold Italic，交付方标注 SIL OFL）。标题优先使用思源宋体 / Noto Serif SC，正文优先使用思源黑体 / Noto Sans SC。未随包提供字体文件；独立维护页使用本地字体栈，缺少指定字体时回退到系统宋体与黑体，不请求在线字体。

## 使用规则

1. 页眉优先使用横版字标；主标志优先使用渐变版。
2. 深色或珊瑚背景使用反白版。不倾斜、不拉伸、不改色。
3. 标志四周留白至少为图标高度的 50%；保证与背景的对比度。
4. 网页资源使用 `/brand/rightwrite/svg/…` 或对应 PNG 路径，不直接引用工作区外层文件。
5. 维护页 `deploy/maintenance.html` 将正式横版字标、渐变标志和珊瑚 App 图标原始 SVG 以 Base64 data URI 内嵌，保证停机时无需额外请求。更新这三份 SVG 时，同步替换维护页中 `.brand`、`.mark` 和 favicon 对应的 data URI；保持原始 SVG 内容与比例，不手工重画字标。

本次接入范围是升级维护页。现有应用各页面的视觉迁移需按后续具体任务处理；正式素材统一从本目录查找。
