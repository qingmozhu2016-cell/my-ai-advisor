import os
import glob
import yfinance as yf
import feedparser
from google import genai
from datetime import datetime
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
import markdown

# --- 1. 基础配置 ---
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=API_KEY)

# 邮箱配置
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = os.environ.get("EMAIL_USER", "").strip()
EMAIL_PASS = os.environ.get("EMAIL_PASS", "").strip()
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip()

# 路径配置
OBSIDIAN_PATH = "./knowledge_base"
REPORT_DIR = "./AI_Reports"

# --- 2. 移动端适配样式 (CSS) ---
# 重点修改：字号适配、边距缩小、表格紧凑化
HTML_STYLE = """
<style>
    /* 全局容器：适配手机屏幕 */
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        line-height: 1.6;
        color: #333;
        margin: 0 auto;
        padding: 10px 15px; /* 手机端保留适量边距 */
        max-width: 600px;   /* 电脑端限制最大宽度，防止太宽 */
        font-size: 16px;    /* 正文适读字号 */
    }
    
    /* 标题样式优化 */
    h1 {
        font-size: 22px;
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 10px;
        margin-top: 0;
    }
    h2 {
        font-size: 19px;
        color: #e67e22;
        margin-top: 25px;
        border-left: 4px solid #e67e22;
        padding-left: 10px;
        background-color: #fff8f0; /* 增加淡背景突出 */
        padding: 5px 10px;
    }
    h3 { font-size: 17px; color: #2980b9; margin-top: 20px; }

    /* 表格关键优化：紧凑模式 */
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        font-size: 13px; /* 缩小字号以容纳更多列 */
    }
    th {
        background-color: #f4f6f7;
        color: #333;
        font-weight: bold;
        padding: 8px 4px; /* 减小内边距 */
        border: 1px solid #e1e4e8;
        text-align: center;
        white-space: nowrap; /* 表头不换行 */
    }
    td {
        padding: 8px 4px;
        border: 1px solid #e1e4e8;
        text-align: center;
    }
    /* 偶数行斑马纹 */
    tr:nth-child(even) { background-color: #fbfbfc; }

    /* 其他元素优化 */
    blockquote {
        border-left: 3px solid #ccc;
        margin: 15px 0;
        padding: 8px 12px;
        color: #555;
        background: #f9f9f9;
        font-size: 15px;
    }
    strong { color: #c0392b; font-weight: 600; }
    
    /* 底部页脚 */
    .footer {
        margin-top: 30px;
        font-size: 12px;
        color: #999;
        text-align: center;
        border-top: 1px dashed #ddd;
        padding-top: 15px;
    }
    
    /* 针对超小屏幕的微调 */
    @media screen and (max-width: 400px) {
        body { padding: 8px; }
        h1 { font-size: 20px; }
        table { font-size: 12px; }
    }
</style>
"""

def get_market_data():
    """获取核心资产数据 (逻辑不变)"""
    print("📊 正在获取行情...")
    tickers = {
        '000001.SS': '🇨🇳 上证', # 缩短名称以适应手机
        '399006.SZ': '🇨🇳 创业板',
        'CNY=X': '💱 汇率', 
        'FXI': '🇨🇳 A50',
        '^TNX': '🇺🇸 美债',
        'GC=F': '🟡 黄金',
        'BTC-USD': '🪙 BTC'
    }
    try:
        data = yf.download(list(tickers.keys()), period="5d", progress=False)
        df = data['Close'] if 'Close' in data else data
