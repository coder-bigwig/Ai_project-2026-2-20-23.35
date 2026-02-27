# init_db.py - 数据库初始化脚本

import asyncio
import os
import requests
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import _hash_password
from app.repositories.user_repository import AuthUserRepository
from app.storage_config import DATABASE_URL

API_URL = "http://localhost:8000/api"

# 示例实验数据
INITIAL_EXPERIMENTS = [
    {
        "title": "Python 基础语法练习",
        "description": "本实验旨在帮助你熟悉 Python 的基本语法，包括变量、数据类型、控制流等。",
        "difficulty": "初级",
        "tags": ["Python", "基础", "语法"],
        "notebook_path": "course/python-basics.ipynb",
        "resources": {"cpu": 0.5, "memory": "1G", "storage": "512M"},
        "deadline": (datetime.now() + timedelta(days=7)).isoformat()
    },
    {
        "title": "Pandas 数据分析入门",
        "description": "学习使用 Pandas 库进行基本的数据处理和分析操作，包括 DataFrame 的创建、索引、过滤等。",
        "difficulty": "中级",
        "tags": ["Data Science", "Pandas", "数据分析"],
        "notebook_path": "course/pandas-intro.ipynb",
        "resources": {"cpu": 1.0, "memory": "2G", "storage": "1G"},
        "deadline": (datetime.now() + timedelta(days=14)).isoformat()
    },
    {
        "title": "机器学习模型训练实战",
        "description": "使用 Scikit-learn 构建一个简单的分类模型，并在真实数据集上进行训练和评估。",
        "difficulty": "高级",
        "tags": ["Machine Learning", "Scikit-learn", "AI"],
        "notebook_path": "course/ml-training.ipynb",
        "resources": {"cpu": 2.0, "memory": "4G", "storage": "2G"},
        "deadline": (datetime.now() + timedelta(days=21)).isoformat()
    }
]

def resolve_seed_creator() -> str:
    """优先使用管理员账号作为实验创建者，避免权限不足。"""
    preferred = (os.getenv("SEED_CREATOR") or "").strip()
    if preferred:
        return preferred

    admin_accounts = (os.getenv("ADMIN_ACCOUNTS") or "").strip()
    for candidate in admin_accounts.split(","):
        username = candidate.strip()
        if username:
            return username

    teacher_accounts = (os.getenv("TEACHER_ACCOUNTS") or "").strip()
    for candidate in teacher_accounts.split(","):
        username = candidate.strip()
        if username:
            return username

    return "fit_admin"


def _to_async_driver_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def _parse_accounts(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


async def ensure_default_auth_users() -> None:
    """首次空库时写入默认 admin/teacher 账号，避免初始化实验时报权限不足。"""
    async_url = _to_async_driver_url(DATABASE_URL)
    if not async_url:
        raise RuntimeError("DATABASE_URL 未配置，无法初始化默认账号")

    admins = _parse_accounts(os.getenv("ADMIN_ACCOUNTS", "fit_admin"))
    teachers = _parse_accounts(
        os.getenv("TEACHER_ACCOUNTS", "teacher_001,teacher_002,teacher_003,teacher_004,teacher_005")
    )
    default_password = os.getenv("DEFAULT_PASSWORD", "fit350506")
    default_hash = _hash_password(default_password)

    engine = create_async_engine(async_url, pool_pre_ping=True, future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    created_count = 0
    updated_count = 0
    try:
        async with session_maker() as db:
            repo = AuthUserRepository(db)

            async def upsert_user(username: str, role: str):
                nonlocal created_count, updated_count
                existing = await repo.get_by_login_identifier(username)
                if existing is not None:
                    changed = False
                    if (existing.role or "").lower() != role:
                        existing.role = role
                        changed = True
                    if not (existing.password_hash or "").strip():
                        existing.password_hash = default_hash
                        changed = True
                    if not existing.is_active:
                        existing.is_active = True
                        changed = True
                    if not (existing.username or "").strip():
                        existing.username = username
                        changed = True
                    if changed:
                        updated_count += 1
                    return

                await repo.upsert_by_email(
                    {
                        "id": str(uuid.uuid4()),
                        "email": f"{username}@local.test",
                        "username": username,
                        "role": role,
                        "password_hash": default_hash,
                        "is_active": True,
                        "created_at": datetime.now(),
                        "updated_at": datetime.now(),
                    }
                )
                created_count += 1

            for username in admins:
                await upsert_user(username, "admin")
            for username in teachers:
                await upsert_user(username, "teacher")

            await db.commit()
    finally:
        await engine.dispose()

    print(f"默认账号检查完成: 新建 {created_count}，更新 {updated_count}")

def wait_for_api():
    """等待 API 服务启动"""
    print("等待 API 服务启动...")
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get("http://localhost:8000/")
            if response.status_code == 200:
                print("API 服务已就绪!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        
        time.sleep(2)
        print(f"重试 {i+1}/{max_retries}...")
    
    print("API 服务启动超时")
    return False

def init_data():
    """初始化数据"""
    asyncio.run(ensure_default_auth_users())

    if not wait_for_api():
        return

    print("开始初始化实验数据...")
    seed_creator = resolve_seed_creator()
    print(f"使用创建者账号: {seed_creator}")
    
    try:
        # 检查是否已有数据
        response = requests.get(f"{API_URL}/experiments")
        existing_experiments = response.json()
        
        if len(existing_experiments) > 0:
            print(f"检测到已有 {len(existing_experiments)} 个实验，跳过初始化")
            return

        # 创建新实验
        for exp in INITIAL_EXPERIMENTS:
            payload = dict(exp)
            payload["created_by"] = seed_creator

            resp = requests.post(f"{API_URL}/experiments", json=payload)
            if resp.status_code == 200:
                print(f"成功创建实验: {payload['title']}")
            else:
                print(f"创建实验失败: {payload['title']}, 错误: {resp.text}")
                
        print("数据初始化完成!")
        
    except Exception as e:
        print(f"初始化过程中出错: {str(e)}")

if __name__ == "__main__":
    init_data()
