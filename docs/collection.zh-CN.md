# 采集与统计口径

[English](collection.md) · [文档目录](README.zh-CN.md)

默认通过 Navidrome 的 `getNowPlaying` API 采集客户端上报的播放活动。统计取决于服务器收到的上报；离线播放或未上报的活动可能无法记录。每组来源只运行一个采集实例。

## 播放计数方式

当累计有效播放时长达到 `PLAY_THRESHOLD_SEC` 时，一首曲目计为一次播放。暂停或暂时消失的时间不计入时长；超过有效推断上限（`MAX_INFERRED_INTERVAL_SEC` 与两倍 `POLL_INTERVAL` 中的较大值）的间隔视为未观察缺口，不增加收听时长，并把保存时长标记为下限。达到阈值时会创建检查点，之后的检查点与会话结算只更新同一条数据库记录，不会重复增加播放次数。

服务器声明支持 OpenSubsonic `playbackReport` 扩展时，媒体位置和播放状态可提高时长统计质量；其他服务器继续使用常规轮询。未达到播放阈值便结束的会话会单独记录为播放尝试。

“最近播放”中的信息按钮会显示这类短会话占已追踪播放尝试的比例。安装前回填和原生历史导入不属于应用采集的实时会话，因此不进入该比例；从 Navidrome Stat 隐私归档恢复的记录则保留原有的计数属性。

## 恢复安装前的收听历史

可选：在已保存的服务器连接上填写一个 Navidrome 智能播放列表（`.nsp`，如「最近播放」）。服务会通过公开的 `getPlaylist` API 定期读取它，并按每首曲目的最后播放时间导入一条记录，其实际收听时长与转码状态保持未知。重复运行绝不产生重复行，实时轮询已覆盖的收听会被跳过，且只导入安装前真实发生过的播放——playCount 暗示的更早次数不会被虚构。到设置页对相应连接填写播放列表 ID 即可启用。

## 从 Navidrome 推送采集

要采集 Navidrome 发出的 scrobble，请设置 `LISTENBRAINZ_INGEST_TOKEN` 与 `LISTENBRAINZ_INGEST_USERNAME`，重启 Navidrome Stat，再把 Navidrome 的 [`ListenBrainz.BaseURL`](https://www.navidrome.org/docs/usage/features/scrobbling/)（或 `ND_LISTENBRAINZ_BASEURL`）指向 `http://navidrome-stat:39421/1/`，并在该 Navidrome 用户的 ListenBrainz 设置中填入采集 token。请求使用标准的 `Authorization: Token` 请求头认证。接收器保存 `single` 与 `import` 提交；`playing_now` 只校验、不保存。

完全相同的重试会按来源、用户名、时间戳、录音与发行标识去重。轮询、播放列表回填、历史导入和该接口收到的记录彼此独立。同一用户不应同时启用多种实时采集方式，除非预期得到多份记录。

## 时长如何显示

详情中的 `≈` 表示估算时长，`≥` 表示目前只能确认的下限，`—` 表示未记录时长。仪表盘和收听回顾的总量直接显示已保存的时长。没有时长的导入记录仍计入播放次数，不增加收听时长。

安装前回填只能补回上游实际提供的记录，无法还原完整历史。v0.9.3 中的 `getSongHistory` 适配器属于实验功能，仅在服务器声明支持相应接口时尝试导入；普通部署不应依赖它。
