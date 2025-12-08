# 飞书通知工具 (feishu-notify)

一个**热插拔**、**灵活**、**易用**的飞书卡片通知工具。

## 特性

- 🎨 **6 级消息分类**：CRITICAL / ERROR / WARNING / SUCCESS / INFO / PENDING
- 🔌 **热插拔模板**：创建 JSON 模板文件即可自动生成调用方法
- 📝 **配置与内容分离**：颜色/Emoji 由级别决定，模板只关心内容结构
- 🚀 **同步/异步发送**：支持 `async/await`
- 🔁 **自动重试**：发送失败自动重试
- 🎯 **去重 & 限流**：避免消息刷屏

## 安装

```bash
pip install httpx jinja2

# 或从源码安装
pip install -e .
```

## 快速开始

### 0. 运行示例 (一键测试)

```bash
# 设置环境变量
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id"

# 直接运行示例
python examples/basic_usage.py
```

### 1. 配置 Webhook

```bash
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id"
```

### 2. 使用内置级别发送

```python
from notifier import Notifier

notifier = Notifier(webhook="https://...", source="Airflow")

# 6 种内置级别
notifier.critical("生产数据库宕机", content="需立即处理！")  # 红色，自动@所有人
notifier.error("ETL任务失败", error_msg="NullPointer...")    # 橙色
notifier.warning("数据延迟预警", content="延迟 45 分钟")     # 黄色
notifier.success("数据同步完成", metrics={"rows": 15000})    # 绿色
notifier.info("任务已启动", content="开始处理...")           # 蓝色
notifier.pending("权限申请", content="请审批")               # 紫色
```

### 3. 使用自定义模板（热插拔）

只需创建 JSON 模板文件，即可自动获得调用方法：

```python
# 假设你创建了 templates/custom/timeout_warning.json
notifier.timeout_warning("任务超时", task_name="sync_job", duration="45min")

# 模板中指定了 default_level: WARNING，所以卡片是黄色的
# 你也可以覆盖级别：
notifier.timeout_warning("严重超时", level=NotifyLevel.ERROR)  # 变成橙色
```

---

## 项目结构

```
feishu-notify/
├── __init__.py              # 主入口导出
├── notifier.py              # Notifier 类
├── config/
│   ├── __init__.py          # 配置类 NotifyConfig
│   └── levels.json          # 级别配置（颜色、emoji、前缀）
├── core/
│   ├── types.py             # 类型定义
│   ├── builder.py           # 卡片构建器
│   ├── sender.py            # 发送器
│   └── dedup.py             # 去重限流
├── templates/
│   ├── loader.py            # 模板加载器
│   ├── base/                # 默认模板（按级别）
│   │   └── *.json
│   └── custom/              # 自定义模板（热插拔）
│       └── *.json
├── examples/                # 示例代码（可直接运行）
│   ├── basic_usage.py
│   └── airflow_integration.py
├── README.md
├── pyproject.toml
└── requirements.txt
```

---

## 级别配置

级别配置在 `config/levels.json`，定义了每个级别的颜色、Emoji、前缀等：

```json
{
  "CRITICAL": {
    "priority": "P0",
    "color": "red",
    "emoji": "🚨",
    "prefix": "[紧急]",
    "mention_all_default": true,
    "skip_rate_limit": true
  },
  "WARNING": {
    "priority": "P2",
    "color": "yellow",
    "emoji": "⚠️",
    "prefix": "[警告]"
  }
  // ...
}
```

| 级别 | 颜色 | Emoji | 说明 |
|------|------|-------|------|
| CRITICAL | 🔴 红色 | 🚨 | 生产事故，自动@所有人 |
| ERROR | 🟠 橙色 | ❌ | 任务失败 |
| WARNING | 🟡 黄色 | ⚠️ | 警告预警 |
| SUCCESS | 🟢 绿色 | ✅ | 成功完成 |
| INFO | 🔵 蓝色 | ℹ️ | 信息通知 |
| PENDING | 🟣 紫色 | ⏳ | 待办审批 |

---

## 自定义模板

### 模板格式

创建 `templates/custom/your_template.json`：

```json
{
  "default_level": "WARNING",
  "title_prefix": "⏰ [超时预警]",
  
  "elements": [
    {
      "tag": "markdown",
      "content": "**预警内容**\n{{ content }}"
    },
    {
      "tag": "div",
      "fields": [
        { "key": "来源系统", "value": "{{ source }}" },
        { "key": "任务名称", "value": "{{ task_name }}" },
        { "key": "已耗时", "value": "{{ duration }}" }
      ]
    },
    {
      "tag": "metrics_block",
      "condition": "{{ metrics }}"
    },
    {
      "tag": "actions",
      "condition": "{{ links }}"
    }
  ],
  
  "footer_note": "⏰ 任务执行时间超过预期，请关注"
}
```

### 关键字段说明

| 字段 | 说明 |
|------|------|
| `default_level` | 默认级别（决定卡片颜色），可被调用时覆盖 |
| `title_prefix` | 自定义标题前缀，替代级别默认的 `[警告]` 等 |
| `elements` | 卡片内容元素列表 |
| `footer_note` | 底部备注信息 |

### 可用元素类型

| tag | 说明 |
|-----|------|
| `markdown` | Markdown 文本块 |
| `div` | 字段列表（key-value 格式） |
| `error_block` | 错误信息块（自动显示 error_code + error_msg） |
| `metrics_block` | 指标数据块（自动格式化 metrics 字典） |
| `extra_fields` | 扩展字段块（自动显示 extra 字典） |
| `actions` | 操作按钮（自动渲染 links 列表） |

### 可用模板变量

```
{{ title }}          - 标题
{{ content }}        - 主要内容
{{ source }}         - 来源系统
{{ task_name }}      - 任务名称
{{ task_id }}        - 任务 ID
{{ timestamp }}      - 时间戳
{{ start_time }}     - 开始时间
{{ end_time }}       - 结束时间
{{ duration }}       - 耗时
{{ error_msg }}      - 错误信息
{{ error_code }}     - 错误代码
{{ metrics }}        - 指标数据（字典）
{{ extra }}          - 扩展字段（字典）
{{ links }}          - 链接列表
{{ level_emoji }}    - 当前级别的 Emoji
{{ level_color }}    - 当前级别的颜色
```

### 使用自定义模板

```python
# 方式 1：直接调用（自动生成方法）
notifier.timeout_warning("任务超时", task_name="sync_job")

# 方式 2：指定级别覆盖
notifier.timeout_warning("严重超时", level=NotifyLevel.ERROR)

# 方式 3：使用 custom() 方法
notifier.custom("timeout_warning", "任务超时", task_name="sync_job")

# 异步版本
await notifier.timeout_warning_async("任务超时")
```

---

## 完整参数

```python
notifier.error(
    title="消息标题",              # 必填
    
    # 内容
    content="主要内容",
    error_msg="错误详情",
    error_code="ERR_001",
    
    # 任务信息
    source="Airflow",
    task_name="daily_etl",
    task_id="task_001",
    
    # 时间
    start_time="2024-01-15 10:00:00",
    end_time="2024-01-15 10:15:00",
    duration="15分钟",
    
    # 指标
    metrics={"rows": 10000, "duration": "5m"},
    
    # 链接按钮
    links=[
        {"text": "查看日志", "url": "https://..."},
        {"text": "重试", "url": "https://...", "is_danger": True},
    ],
    link_url="https://...",  # 快捷方式
    link_text="查看详情",
    
    # @ 提醒
    mentions=["user_id_1"],
    mention_all=True,
    
    # 去重
    dedupe_key="unique-error-id",
    
    # 扩展字段
    extra={"自定义字段": "值"},
)
```

---

## 异步发送

```python
import asyncio
from notifier import Notifier

async def main():
    async with Notifier(webhook="https://...") as notifier:
        await notifier.success_async("异步任务完成")
        await notifier.timeout_warning_async("任务超时")

asyncio.run(main())
```

---

## 配置选项

```python
from notifier import Notifier
from config import NotifyConfig

config = NotifyConfig(
    webhook_url="https://...",
    default_source="DataPlatform",
    
    # 去重
    enable_dedup=True,
    dedup_ttl_seconds=300,      # 5 分钟内相同消息去重
    
    # 限流
    enable_rate_limit=True,
    rate_limit_window=60,       # 60 秒窗口
    rate_limit_max_count=10,    # 最多 10 条
    
    # 重试
    max_retries=3,
    retry_delay=1.0,
    
    # CRITICAL 级别自动 @所有人
    critical_mention_all=True,
)

notifier = Notifier(config=config)
```

---

## 环境变量

| 变量名 | 说明 |
|--------|------|
| `FEISHU_WEBHOOK` | Webhook URL |
| `FEISHU_SOURCE` | 默认消息来源 |
| `FEISHU_TEMPLATE_DIR` | 自定义模板目录 |
| `FEISHU_REDIS_URL` | Redis URL（分布式去重） |

---

## Airflow 集成示例

```python
from notifier import Notifier

notifier = Notifier(webhook="https://...", source="Airflow")

def on_task_failure(context):
    task = context["task_instance"]
    notifier.error(
        title=f"任务失败: {task.task_id}",
        error_msg=str(context.get("exception", "")),
        task_name=task.task_id,
        link_url=f"https://airflow.example.com/log?task_id={task.task_id}",
    )

default_args = {
    'on_failure_callback': on_task_failure,
}
```

---

## 参考资源

- [飞书卡片概述](https://open.feishu.cn/document/feishu-cards/feishu-card-overview)
- [飞书消息卡片设计规范](https://open.feishu.cn/document/tools-and-resources/design-specification/message-card-design-specifications)

## License

MIT
