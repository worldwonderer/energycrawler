# xhs / x 字段对照清单（creator 模式）

> 更新时间：2026-02-23

本文用于核对当前 `xhs` 与 `x` 在 `--type creator` 下的抓取字段、媒体字段与落库字段。

---

## 1. x（X.com / Twitter）

### 1.1 运行方式

```bash
uv run energycrawler crawl -- --platform x --lt cookie --type creator --creator_id "elonmusk"
```

`creator_id` 支持：
- `screen_name`（如 `elonmusk` / `@elonmusk`）
- 数字 `user_id`

### 1.2 输出文件（json/csv/excel）

- 创作者：`data/twitter/json/creator_creators_YYYY-MM-DD.json`
- 推文：`data/twitter/json/creator_contents_YYYY-MM-DD.json`

推文核心字段（creator_contents）：

- 基础：`tweet_id` `tweet_id_str` `text` `created_at`
- 作者：`user_id` `screen_name` `name`
- 计数：`reply_count` `retweet_count` `favorite_count` `bookmark_count` `quote_count` `view_count`
- 关系：`in_reply_to_status_id` `in_reply_to_user_id` `in_reply_to_screen_name`
- 状态：`is_quote_status` `quoted_status_id` `retweeted_status_id` `possibly_sensitive`
- 实体：`hashtags` `urls` `user_mentions`
- 媒体：
  - 扁平字段：`media_urls`（图片 URL，逗号拼接）、`video_urls`（视频/GIF URL，逗号拼接）
  - 结构化字段：`media_detail`（JSON 数组，完整媒体对象）
- 其他：`tweet_url` `source` `lang` `source_keyword`

`media_detail` 子字段：

- `media_key` `media_id` `media_type`
- `media_url` `video_url`
- `display_url` `expanded_url`
- `width` `height` `duration_ms` `view_count`

### 1.3 媒体二进制下载（可选）

当 `ENABLE_GET_MEIDAS=true` 时：

- 下载目录：`data/twitter/media/<tweet_id>/`
- 文件名：`<index>_<media_type>.<ext>`
- `animated_gif` 会优先使用 `video_url`（mp4）下载

### 1.4 DB 表映射（twitter_tweet）

对应表：`twitter_tweet`

新增/重点字段：

- `urls`（Text，JSON 字符串）
- `user_mentions`（Text，JSON 字符串）
- `media_detail`（Text，JSON 字符串）
- `media_urls`（Text）
- `video_urls`（Text）

兼容升级：

- 执行 `--init_db` 时会自动补齐 `urls/user_mentions/media_detail` 缺失列。

---

## 2. xhs（小红书）

### 2.1 运行方式

```bash
uv run energycrawler crawl -- --platform xhs --lt cookie --type creator --creator_id "https://www.xiaohongshu.com/user/profile/xxx?xsec_token=...&xsec_source=..."
```

### 2.2 输出文件（json/csv/excel）

- 创作者：`data/xhs/json/creator_creators_YYYY-MM-DD.json`
- 笔记：`data/xhs/json/creator_contents_YYYY-MM-DD.json`
- 评论：`data/xhs/json/creator_comments_YYYY-MM-DD.json`

笔记字段（creator_contents）：

- 基础：`note_id` `type` `title` `desc`
- 作者：`user_id` `nickname` `avatar`
- 计数：`liked_count` `collected_count` `comment_count` `share_count`
- 时间：`time` `last_update_time`
- 媒体：`image_list`（逗号拼接） `video_url`（逗号拼接）
- 其他：`ip_location` `tag_list` `note_url` `xsec_token` `source_keyword`

评论字段（creator_comments）：

- `comment_id` `note_id` `content` `create_time`
- `user_id` `nickname` `avatar`
- `like_count` `sub_comment_count`
- `pictures`
- `parent_comment_id`（一级评论为 `0`，子评论为根评论 ID）

创作者字段（creator_creators）：

- `user_id` `nickname` `gender` `avatar` `desc` `ip_location`
- `follows` `fans` `interaction`
- `tag_list`

### 2.3 媒体二进制下载（可选）

当 `ENABLE_GET_MEIDAS=true` 时：

- 图片：`data/xhs/images/<note_id>/<index>.jpg`
- 视频：`data/xhs/videos/<note_id>/<index>.mp4`

注意：
- 已修复“无图笔记提前 return 导致视频不下载”的问题。

### 2.4 DB 表映射

- 笔记表：`xhs_note`
- 评论表：`xhs_note_comment`（含一级评论与子评论）
- 创作者表：`xhs_creator`

重点说明：

- `xhs_note.image_list` / `xhs_note.tag_list` 不再二次 JSON 编码
- `xhs_note_comment.pictures` 不再二次 JSON 编码
- `xhs_creator.tag_list` 已做兼容归一，避免字符串再次 `json.dumps`

---

## 3. 已修复的关键缺漏（本轮）

- x `creator` 模式改为按博主抓推文（非仅用户信息）
- x 支持 `screen_name -> user_id` 自动解析
- x 补齐 `urls/user_mentions/media_detail` 全链路（解析 → 输出 → DB）
- x `animated_gif` 提取并使用 `video_url`
- xhs 修复指定笔记配置键读取错误
- xhs 修复子评论分页尾页丢失
- xhs 修复无图时视频下载被跳过
- xhs 补齐 json/csv 的 creator 输出

