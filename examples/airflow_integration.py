#!/usr/bin/env python3
"""
飞书通知工具 - Airflow 集成示例

展示如何在 Airflow DAG 中使用飞书通知

使用方法:
    1. 将此文件复制到 Airflow DAGs 目录
    2. 设置环境变量: export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id"
"""

import os
import sys
from datetime import datetime
from typing import Any, Dict

# 添加项目根目录到 Python 路径，支持直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notifier import Notifier
from core.types import NotifyLevel, NotifyMessage


# 全局通知器（建议在 Airflow 配置中统一管理）
WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK", "")
notifier = Notifier(webhook=WEBHOOK_URL, source="Airflow") if WEBHOOK_URL else None


def on_task_success(context: Dict[str, Any]):
    """任务成功回调"""
    if not notifier:
        return
        
    task_instance = context["task_instance"]
    dag_id = context["dag"].dag_id
    task_id = task_instance.task_id
    execution_date = context["execution_date"]
    
    notifier.success(
        title=f"任务成功: {dag_id}.{task_id}",
        content=f"DAG `{dag_id}` 的任务 `{task_id}` 执行成功",
        task_name=task_id,
        task_id=f"{dag_id}_{task_id}",
        extra={
            "DAG": dag_id,
            "Task": task_id,
            "执行日期": str(execution_date),
        },
        link_url=f"https://airflow.example.com/task?dag_id={dag_id}&task_id={task_id}",
    )


def on_task_failure(context: Dict[str, Any]):
    """任务失败回调"""
    if not notifier:
        return
        
    task_instance = context["task_instance"]
    dag_id = context["dag"].dag_id
    task_id = task_instance.task_id
    execution_date = context["execution_date"]
    exception = context.get("exception")
    
    # 获取错误信息
    error_msg = str(exception) if exception else "Unknown error"
    
    # 获取日志链接
    log_url = f"https://airflow.example.com/log?dag_id={dag_id}&task_id={task_id}&execution_date={execution_date}"
    
    notifier.error(
        title=f"任务失败: {dag_id}.{task_id}",
        error_msg=error_msg,
        task_name=task_id,
        task_id=f"{dag_id}_{task_id}",
        extra={
            "DAG": dag_id,
            "Task": task_id,
            "执行日期": str(execution_date),
            "重试次数": task_instance.try_number,
        },
        links=[
            {"text": "查看日志", "url": log_url},
            {"text": "重试任务", "url": f"https://airflow.example.com/retry?dag_id={dag_id}&task_id={task_id}"},
        ],
        dedupe_key=f"airflow_{dag_id}_{task_id}_{execution_date}",
    )


def on_dag_success(context: Dict[str, Any]):
    """DAG 成功回调"""
    if not notifier:
        return
        
    dag_id = context["dag"].dag_id
    execution_date = context["execution_date"]
    
    notifier.success(
        title=f"DAG 执行完成: {dag_id}",
        content=f"DAG `{dag_id}` 已成功执行完成",
        extra={
            "DAG": dag_id,
            "执行日期": str(execution_date),
            "总任务数": len(context["dag"].tasks),
        },
        link_url=f"https://airflow.example.com/graph?dag_id={dag_id}",
    )


def on_sla_miss(dag, task_list, blocking_task_list, slas, blocking_tis):
    """SLA 超时回调"""
    if not notifier:
        return
        
    dag_id = dag.dag_id
    
    notifier.warning(
        title=f"SLA 超时警告: {dag_id}",
        content=f"DAG `{dag_id}` 的部分任务超过了预定的 SLA 时间",
        extra={
            "DAG": dag_id,
            "超时任务": ", ".join([t.task_id for t in task_list]),
        },
        link_url=f"https://airflow.example.com/sla?dag_id={dag_id}",
    )


# ==================== DAG 定义示例 ====================
"""
# 以下是 Airflow DAG 定义示例（需要 Airflow 环境）

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    'owner': 'data_team',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'on_failure_callback': on_task_failure,
    'on_success_callback': on_task_success,
}

with DAG(
    dag_id='example_dag_with_feishu',
    default_args=default_args,
    description='Example DAG with Feishu notifications',
    schedule_interval='0 8 * * *',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    on_success_callback=on_dag_success,
    sla_miss_callback=on_sla_miss,
) as dag:
    
    task1 = PythonOperator(
        task_id='extract_data',
        python_callable=lambda: print("Extracting data..."),
    )
    
    task2 = PythonOperator(
        task_id='transform_data',
        python_callable=lambda: print("Transforming data..."),
    )
    
    task3 = PythonOperator(
        task_id='load_data',
        python_callable=lambda: print("Loading data..."),
    )
    
    task1 >> task2 >> task3
"""


# ==================== 通用装饰器 ====================

def notify_on_error(title_prefix: str = "任务失败"):
    """
    装饰器：任务执行失败时发送飞书通知
    
    Usage:
        @notify_on_error("数据处理失败")
        def my_task():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if notifier:
                    notifier.error(
                        title=f"{title_prefix}: {func.__name__}",
                        error_msg=str(e),
                        task_name=func.__name__,
                        dedupe_key=f"error_{func.__name__}",
                    )
                raise
        return wrapper
    return decorator


def notify_on_complete(title: str = None):
    """
    装饰器：任务执行完成时发送飞书通知
    
    Usage:
        @notify_on_complete("数据同步完成")
        def my_task():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            import time
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                if notifier:
                    notifier.success(
                        title=title or f"任务完成: {func.__name__}",
                        content=f"任务 `{func.__name__}` 执行成功",
                        task_name=func.__name__,
                        duration=f"{elapsed:.2f}s",
                    )
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                if notifier:
                    notifier.error(
                        title=f"任务失败: {func.__name__}",
                        error_msg=str(e),
                        task_name=func.__name__,
                        duration=f"{elapsed:.2f}s",
                    )
                raise
        return wrapper
    return decorator


# ==================== 使用示例 ====================

if __name__ == "__main__":
    if not WEBHOOK_URL:
        print("❌ 请先设置环境变量 FEISHU_WEBHOOK")
        print("   export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id'")
        sys.exit(1)
    
    print("=" * 60)
    print("飞书通知工具 - Airflow 集成示例")
    print("=" * 60)
    
    @notify_on_complete("示例任务完成")
    def example_task():
        print("执行示例任务...")
        return "success"
    
    @notify_on_error("示例任务失败")
    def failing_task():
        print("执行会失败的任务...")
        raise ValueError("Something went wrong!")
    
    # 运行成功任务
    print("\n📤 运行成功任务装饰器...")
    example_task()
    print("✅ 成功任务执行完成")
    
    # 运行失败任务（取消注释以测试）
    # print("\n📤 运行失败任务装饰器...")
    # try:
    #     failing_task()
    # except ValueError:
    #     print("❌ 预期的异常已捕获")
    
    print("\n" + "=" * 60)
    print("✅ Airflow 集成示例执行完成！")
    print("=" * 60)

