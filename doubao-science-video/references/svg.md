# SVG / HTML 动画到科普成片

适用：剖面、结构拆解、生长路径、器官分工等可用明确几何和时间轴讲清的内容。优先选择本地程序动画；无需为填满成片而调用视频模型。SVG只是一种图形技术，科学内容仍需审核，不能把平面示意称为真实3D或物理仿真。

## 制作约定

使用可信的本地 HTML 文件，内嵌 SVG、CSS 和 JavaScript；不要将外部下载的未知网页当可执行动画。导出器只服务输入文件所在目录（不暴露整个项目），阻止外部网络请求，不读取凭据。依赖字体和图片应在本地可用，不采用随机数、Date.now 或网络状态控制画面。

页面应提供：

- `#stage`：固定1280×720的画面区域，控制栏放在区域外。
- `window.animationDuration`：动画总秒数。
- `window.renderFrame(seconds)`：根据绝对时间设置所有画面属性。可返回Promise；相同时间重复或乱序调用必须得到同样画面，不依赖上一次帧或实时播放状态。
- 导出模式 `?export=1`：关闭自动播放与计时器；交互预览可有播放、暂停、拖动和拆解按钮。

静态SVG可以在HTML里包一层空操作的 `renderFrame`，配合duration导出定格。已有CSS/SMIL动画须显式暂停并根据传入时间seek；本脚本不会猜测或自动转换任意SVG的时间轴。声音和字幕由后续合成脚本统一处理。

## 依赖与命令

需要 Node.js、Playwright、Chrome/Chromium 和 FFmpeg。已有 Playwright 可设置 `PLAYWRIGHT_MODULE` 为模块路径；否则在本Skill的scripts目录安装：

```bash
npm install --prefix /path/to/doubao-science-video/scripts --no-save playwright
# 使用系统 Chrome 时带 --channel chrome；或安装 Playwright Chromium：
/path/to/doubao-science-video/scripts/node_modules/.bin/playwright install chromium
```

执行：

```bash
node scripts/export_svg.mjs assets/sunflower-svg/scene.html \
  --output /path/to/output/silent.mp4 --channel chrome
```

默认打开独立可见浏览器，不使用日常登录资料；需要后台渲染时显式加 `--headless`。可选 `--duration`、`--fps`、`--width`、`--height`；页面stage尺寸须匹配。默认25fps/1280×720；总帧数向上取整，最多增加不足一帧时长。

每帧调用 `renderFrame(i/fps)`，截图直接流入FFmpeg，无需保存成百上千张PNG。输出H.264静音MP4和 `.mp4.report.json`（帧数、规格、渲染耗时、0次模型调用）。已有输出时拒绝覆盖；中间文件放到指定输出目录下的临时文件夹，结束自动清理。导出不是实时录屏，不因渲染慢而丢帧。

将silent.mp4作为 [render.md](render.md) 的 `video` 输入，配合实际音频时长、口播和cues调用 `render.py`，即可加配音、字幕和AI标识。多段口播可使用同一silent.mp4的不同in/out区间。为避免意外减速，每段动画区间应与音频时长加尾停顿匹配。参考模板在 `assets/sunflower-svg/scene.html`，提供两阶段动画和拆解按钮；含配音版本需自行提供合法音频，本包不附密钥或独立音频素材。

## 验收与成本

先抽查开头、关键变化和结尾，检查播放/暂停、拖动及拆装；对同一时间重复截图验证确定性。导出后走合成脚本整片解码，实际播放成片，检查口播与动作同步、字幕留白和AI标识。交互功能保留在HTML，MP4本身不可点击拆装。

纯SVG画面不产生视频生成API费用，重复渲染也不消耗视频额度；仍有Agent使用、代码制作、本地CPU/电力和可能的TTS费用。缓存已审核画面与配音可避免重复调用。20元预算仍约束实际付费图片/语音/视频调用，不把本地渲染的0模型调用费说成总制作成本为0。报告实测渲染耗时，不编造电费或包含所有成本的每条固定价格。
