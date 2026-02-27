# init_db.py - 数据库初始化脚本

import os
import requests
import time
from datetime import datetime, timedelta

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
    if not wait_for_api():
        return

    print("开始初始化实验数据...")
    
    try:
        # 检查是否已有数据
        response = requests.get(f"{API_URL}/experiments")
        existing_experiments = response.json()
        
        if len(existing_experiments) > 0:
            print(f"检测到已有 {len(existing_experiments)} 个实验，跳过初始化")
            return

        # 创建新实验
        for exp in INITIAL_EXPERIMENTS:
            exp["created_by"] = "admin"  # 这里假设 created_by 是必需的
            # 注意：datetime 对象已经转换为 isoformat 字符串
            
            resp = requests.post(f"{API_URL}/experiments", json=exp)
            if resp.status_code == 200:
                print(f"成功创建实验: {exp['title']}")
            else:
                print(f"创建实验失败: {exp['title']}, 错误: {resp.text}")
                
        print("数据初始化完成!")
        
    except Exception as e:
        print(f"初始化过程中出错: {str(e)}")

if __name__ == "__main__":
    init_data()
