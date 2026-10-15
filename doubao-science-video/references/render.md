# 本地合成脚本

需要 Python 3、FFmpeg（含 libx264、libass），建议同时安装 FFprobe；未安装时脚本使用 FFmpeg 元数据回退。系统需系统已安装可显示中文的字体。先用 `ffmpeg -filters` 核对 ass 过滤器；渲染后检查中文是否缺字，可在 manifest 的 font 设为已安装字体名。

输入 manifest 中的媒体路径相对于 manifest 所在目录。所有媒体须已下载、经科学正确性与声音内容审核。脚本不生成素材，也不负责精确字幕对齐。

```json
{
  "font": "sans-serif",
  "subtitle_timing_method": "manual_after_listening",
  "segments": [
    {
      "id": "01",
      "video": "clips/01.mp4",
      "audio": "audio/01.mp3",
      "in": 0,
      "out": 5,
      "narration": "最先探出来的是胚根。它会成为根系的一部分。",
      "cues": [
        {"start": 0.1, "end": 2.5, "text": "最先探出来的是胚根。"},
        {"start": 2.5, "end": 5.0, "text": "它会成为根系的一部分。"}
      ]
    }
  ]
}
```

示例时间仅展示结构，须替换为真实媒体范围。每段自动加0.4秒尾停顿。`in/out` 选择已审核的视频区间；最长减速到1.5倍时长，其余用末帧定格，避免倒放生长过程。若源镜头长于音频则截短，执行前须确认关键变化没有被截掉。输入画面原声音轨不保留，使用指定配音；不自动加背景音乐。

```bash
python3 scripts/render.py /path/to/manifest.json --output /path/to/final.mp4
```

输出：MP4、同名SRT、同名report.json。成片包含持续AI标识，采用1280×720/25fps、H.264/AAC mono48k，逐段响度目标-16LUFS。脚本验证字幕拼接等于口播、时间不重叠且不超范围、输入确有音视频流，完成后整片解码。已有输出或附属文件时拒绝覆盖；中间文件使用临时目录并自动清理。

报告的 `rendered_and_decoded` 仅代表技术检查完成，`human_review` 仍为 pending。需播放检查科学内容、字幕读速、中文字体、口播清晰度、段落衔接和AI标识可见性后，才向用户宣称验收完成。响度滤镜目标不等于实测响度，若报告数值应另行测量。
