# Excel 导出指南

## 概述

EnergyCrawler 支持将抓取结果导出为 `.xlsx` 文件，自动拆分工作表并带基础格式化。

## 支持范围

- 平台：`xhs`、`x`
- 数据类型：`contents`、`comments`、`creators`

## 快速使用

1. 配置导出格式：

```python
# config/base_config.py
SAVE_DATA_OPTION = "excel"
```

2. 运行任务：

```bash
# xhs 示例
uv run main.py --platform xhs --lt qrcode --type search --save_data_option excel

# x 示例
uv run main.py --platform x --lt cookie --type search --save_data_option excel
```

3. 查看输出文件：

- 目录：`data/{platform}/`
- 文件名：`{platform}_{crawler_type}_{timestamp}.xlsx`

## 导出结构

- `Contents`：帖子/推文主体信息
- `Comments`：评论信息
- `Creators`：创作者信息

空表会在最终保存时自动移除。

## 常见问题

### 1. 文件未生成

检查：

- `SAVE_DATA_OPTION` 是否为 `excel`
- 当前任务是否抓到数据
- 运行日志是否有异常

### 2. 列宽或样式不符合预期

当前使用内置默认样式，如需自定义可扩展 `store/excel_store_base.py`。

### 3. 如何继续做数据分析

可直接用以下工具打开：

- Microsoft Excel
- Google Sheets
- LibreOffice
- Python `pandas.read_excel`
