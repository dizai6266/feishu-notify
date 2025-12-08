#!/usr/bin/env python3
"""
飞书通知工具 - 基础使用示例

展示最常用的发送场景

使用方法:
    1. 设置环境变量: export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id"
    2. 直接运行: python basic_usage.py
"""

import asyncio
import os
import sys

# 添加项目根目录到 Python 路径，支持直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notifier import Notifier
from core.types import NotifyLevel, NotifyMessage


# 从环境变量获取 Webhook URL
WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK", "")

if not WEBHOOK_URL:
    print("❌ 请先设置环境变量 FEISHU_WEBHOOK")
    print("   export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id'")
    sys.exit(1)


def sync_examples():
    """同步发送示例"""
    
    # 创建通知器
    notifier = Notifier(webhook=WEBHOOK_URL, source="示例系统")
    
    # 1. 发送成功通知
    result = notifier.success(
        title="数据同步任务完成",
        content="用户订单数据已成功同步到数据仓库",
        task_name="sync_user_orders",
        task_id="task_20240115_001",
        start_time="2024-01-15 10:00:00",
        end_time="2024-01-15 10:15:32",
        duration="15分32秒",
        metrics={"rows": 152345, "tables": 3},
        link_url="https://airflow.example.com/task/123",
        link_text="查看任务详情",
    )
    print(f"✅ 成功通知: {result.success} - {result.message}")
    
    # 2. 发送错误通知
    result = notifier.error(
        title="ETL任务执行失败",
        error_msg="NullPointerException: Cannot invoke method on null object\n    at DataProcessor.transform(DataProcessor.java:152)",
        task_name="daily_etl_pipeline",
        error_code="ETL_001",
        links=[
            {"text": "查看日志", "url": "https://logs.example.com/search?id=abc"},
            {"text": "重试任务", "url": "https://airflow.example.com/retry/456"},
        ],
    )
    print(f"❌ 错误通知: {result.success} - {result.message}")
    
    # 3. 发送警告通知
    result = notifier.warning(
        title="数据延迟预警",
        content="订单表数据同步延迟超过阈值，当前延迟 45 分钟（阈值: 30 分钟）",
        extra={
            "当前延迟": "45 分钟",
            "阈值": "30 分钟",
            "数据表": "ods.orders",
        },
    )
    print(f"⚠️  警告通知: {result.success} - {result.message}")
    
    # 4. 发送信息通知
    result = notifier.info(
        title="每日数据报告已生成",
        content="2024年1月15日的销售数据报告已生成，请查阅",
        link_url="https://bi.example.com/reports/daily/20240115",
    )
    print(f"ℹ️  信息通知: {result.success} - {result.message}")
    
    # 5. 发送紧急告警
    result = notifier.critical(
        title="生产数据库连接池耗尽",
        content="MySQL主库连接池使用率达到100%，新请求无法获取连接，需立即处理！",
        error_msg="Pool exhausted: no available connections after 30s timeout",
        mentions=["user123"],  # @ 指定用户
    )
    print(f"🚨 紧急告警: {result.success} - {result.message}")
    
    # 6. 发送待办通知
    result = notifier.pending(
        title="数据导出权限申请",
        content="用户 张三 申请导出「用户行为分析表」的数据，请审批",
        extra={
            "申请人": "张三",
            "申请数据": "用户行为分析表",
            "数据量": "约 50 万行",
        },
        links=[
            {"text": "同意", "url": "https://admin.example.com/approve/789"},
            {"text": "拒绝", "url": "https://admin.example.com/reject/789", "is_danger": True},
        ],
    )
    print(f"⏳ 待办通知: {result.success} - {result.message}")
    
    # 关闭连接
    notifier.close()


async def async_examples():
    """异步发送示例"""
    
    # 使用 async with 自动管理资源
    async with Notifier(webhook=WEBHOOK_URL, source="异步示例") as notifier:
        
        # 异步发送成功通知
        result = await notifier.success_async(
            title="异步任务完成",
            content="批量数据处理已完成",
            metrics={"processed": 10000, "duration": "2m30s"},
        )
        print(f"✅ 异步成功通知: {result.success}")
        
        # 异步发送错误通知
        result = await notifier.error_async(
            title="Spark任务失败",
            error_msg="OutOfMemoryError: Java heap space",
            task_name="spark_analysis_job",
        )
        print(f"❌ 异步错误通知: {result.success}")


def advanced_usage():
    """高级用法示例"""
    
    notifier = Notifier(
        webhook=WEBHOOK_URL,
        source="高级示例",
        enable_dedup=True,      # 启用去重
        enable_rate_limit=True,  # 启用限流
    )
    
    # 使用 NotifyMessage 对象（完全控制）
    message = NotifyMessage(
        level=NotifyLevel.ERROR,
        title="自定义消息",
        content="这是一条使用 NotifyMessage 对象发送的消息",
        source="高级示例",
        task_name="custom_task",
        metrics={"key1": "value1", "key2": 123},
        dedupe_key="custom-dedup-key",  # 自定义去重 key
    )
    
    # 链式调用添加更多属性
    message.add_link("查看详情", "https://example.com/detail")
    message.add_link("删除", "https://example.com/delete", is_danger=True)
    message.add_mention("user456")
    message.set_metrics(extra_metric="value")
    
    result = notifier.send(message)
    print(f"📦 高级用法: {result.success} - {result.message}")
    
    # 发送相同 dedupe_key 的消息（会被去重）
    result = notifier.send(message)
    print(f"🔄 重复消息: {result.success} - {result.message}")  # 应该显示被去重
    
    notifier.close()


def custom_template_examples():
    """自定义模板示例"""
    
    notifier = Notifier(webhook=WEBHOOK_URL, source="自定义模板测试")
    
    # 1. 使用 custom() 方法调用自定义模板
    result = notifier.custom(
        template_name="timeout_warning",
        title="数据同步任务超时",
        content="sync_orders 任务执行超过预期时间",
        task_name="sync_orders",
        duration="45分钟",
        extra={
            "预期时间": "30分钟",
            "已超时": "15分钟",
        },
    )
    print(f"⏰ 超时预警模板: {result.success} - {result.message}")
    
    # 2. 动态方法调用 - 直接用模板名称作为方法名
    # 自动从模板的 default_level 获取颜色
    result = notifier.timeout_warning(
        title="ETL管道执行超时",
        content="daily_etl 任务执行超时",
        task_name="daily_etl",
        duration="2小时",
    )
    print(f"⏰ 动态方法调用: {result.success} - {result.message}")
    
    # 3. 调用时覆盖级别（升级为 ERROR）
    result = notifier.timeout_warning(
        title="关键任务严重超时",
        content="核心报表任务超时严重",
        task_name="core_report",
        duration="5小时",
        level=NotifyLevel.ERROR,  # 覆盖默认的 WARNING 级别
    )
    print(f"❌ 覆盖级别调用: {result.success} - {result.message}")
    
    # 4. 数据质量模板
    result = notifier.data_quality(
        title="订单表数据异常",
        content="发现订单表存在重复数据",
        task_name="ods.orders",
        metrics={
            "重复记录数": 156,
            "影响日期": "2024-01-15",
            "总记录数": 50000,
        },
    )
    print(f"📊 数据质量模板: {result.success} - {result.message}")
    
    notifier.close()


if __name__ == "__main__":
    print("=" * 60)
    print("飞书通知工具 - 基础使用示例")
    print("=" * 60)
    
    print("\n" + "-" * 60)
    print("📤 同步发送示例")
    print("-" * 60)
    sync_examples()
    
    print("\n" + "-" * 60)
    print("📤 异步发送示例")
    print("-" * 60)
    asyncio.run(async_examples())
    
    print("\n" + "-" * 60)
    print("📤 高级用法示例")
    print("-" * 60)
    advanced_usage()
    
    print("\n" + "-" * 60)
    print("📤 自定义模板示例")
    print("-" * 60)
    custom_template_examples()
    
    print("\n" + "=" * 60)
    print("✅ 所有示例执行完成！")
    print("=" * 60)

