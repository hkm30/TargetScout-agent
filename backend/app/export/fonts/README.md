# CJK Font for PDF Export

PDF reports contain Chinese text and require NotoSansSC fonts.

## Quick Setup

```bash
./download_fonts.sh
```

This downloads ~16MB of font files from the [noto-cjk](https://github.com/notofonts/noto-cjk) repository.

## Files (not tracked in git)

- `NotoSansSC-Regular.ttf`
- `NotoSansSC-Bold.ttf` (optional, falls back to Regular)

Without these fonts, PDF export will fail for Chinese content.
