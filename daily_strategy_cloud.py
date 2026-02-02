import os
import glob
import yfinance as yf
import feedparser
from google import genai
from datetime import datetime
import re
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
import pandas as pd

# --- 1. 基础配置 ---
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=API_KEY)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = os.environ.get("EMAIL_USER", "").strip()
EMAIL_PASS = os.environ.get("EMAIL_PASS", "").strip()
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip()

OBSIDIAN_PATH = "./knowledge_base"
REPORT_DIR = "./AI_Reports"

def get_realtime_price(symbol, name):
    """
    核心逻辑：使用 60分钟线 (interval='60m') 强制获取最新数据
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="60m")
        
        if df.empty: return None, None, None

        # 取最新一行
        latest_price = df['Close'].iloc[-1]
        last_date = df.index[-1].date()
        
        # 找“非今日”的最后一行作为昨日收盘
        prev_data = df[df.index.date != last_date]
        
        if not prev_data.empty:
            prev_close = prev_data['Close'].iloc[-1]
            pct_change = ((latest_price - prev_close) / prev_close) * 100
        else:
            prev_close = df['Close'].iloc[0]
            pct_change = 0.0

        return latest_price, pct_change, last_date.strftime("%m-%d")

    except:
        return None, None, None

def get_market_table():
    """生成行情表格"""
    print("📊 正在获取实时行情...")
    tickers = {
        '000001.SS': '🇨🇳 上证指数',
        '399006.SZ': '🇨🇳 创业板指',
        'CNY=X': '💱 美元/人民币', 
        'FXI': '🇨🇳 A50 (ETF)',
        '^TNX': '🇺🇸 10年美债',
        'GC=F': '🟡 黄金期货',
        'BTC-USD': '🪙 比特币'
    }
    
    md_table = "| 资产 | 日期 | 最新价 | 涨跌幅 |\n|---|---|---|---|\n"
    
    for symbol, name in tickers.items():
        price, change, date_str = get_realtime_price(symbol, name)
        
        if price is not None:
            icon = "🔺" if change > 0 else "💚"
            # 格式化
            if "CNY" in symbol: fmt = f"{price:.4f}"
            elif "^" in symbol: fmt = f"{price:.3f}%"
            else: fmt = f"{price:.2f}"
            
            md_table += f"| {name} | {date_str} | {fmt} | {icon} {change:+.2f}% |\n"
        else:
            md_table += f"| {name} | - | 暂无 | - |\n"
            
    return md_table

def get_news_brief():
    """获取新闻 (多抓少取，交给AI筛选)"""
    print("🌍 正在检索财经新闻...")
    news_list = []
    sources = [
        {"name": "联合早报", "url": "https://www.zaobao.com.sg/rss/finance.xml"},
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"}
    ]
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            # 这里虽然抓了前5条，但在 Prompt 里会限制输出数量
            for entry in feed.entries[:5]:
                clean_summary = re.sub('<.*?>', '', getattr(entry, 'summary', '')).strip()
                news_list.append(f"【{src['name']}】{entry.title}")
        except: pass
    return "\n".join(news_list)

def get_obsidian_knowledge():
    """读取知识库"""
    context = ""
    if os.path.exists(OBSIDIAN_PATH):
        for f in glob.glob(os.path.join(OBSIDIAN_PATH, "*.md")):
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    context += f"\n【笔记：{os.path.basename(f)}】\n{file.read()[:2000]}\n"
            except: pass
    return context

def save_and_send(title, content):
    """保存并发送"""
    if not os.path.exists(REPORT_DIR):
        os.makedirs(REPORT_DIR)
    
    filename = f"{REPORT_DIR}/{datetime.now().strftime('%Y-%m-%d')}_AI_Daily.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    if not EMAIL_USER: return
    msg = MIMEText(content, 'plain', 'utf-8')
    msg['Subject'] = title
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        print("✅ 邮件已发送！")
        server.quit()
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    market = get_market_table()
    news = get_news_brief()
    knowledge = get_obsidian_knowledge()
    
    print("🤖 Gemini 正在生成策略...")
    
    prompt = f"""
    【角色】朱文翔（资深理财经理，注重风险控制）。
    【日期】{date_str}
    
    【任务】生成《家庭财富风险管理日报》，Markdown格式。
    
    【输入素材】
    1. 行情：\n{market}
    2. 新闻池：\n{news}
    3. 私人笔记库：\n{knowledge}
    
    【文章结构与约束】
    
    **第一部分：核心资产看板**
    - 展示表格。
    - 一句话简评今日市场情绪。
    
    **第二部分：财经要闻（仅筛选 Top 5）**
    - 从新闻池中精选 **5 条** 对中国家庭财富影响最大的新闻。
    - 格式：`1. [标题]` 
    - 点评：`> 影响分析：...`
    
    **第三部分：策略与建议**
    - 结合上述新闻，给出一条核心的操作建议。
    - **引用约束**：如果笔记库中有极其契合的理论（如反脆弱），**最多引用 1 次**，不要为了引用而引用。如果没有合适的，就直接给出专业建议，不要强行引用。
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        if response.text:
            save_and_send(f"【AI日报】{date_str} 核心行情与策略", response.text)
        else:
            print("❌ 生成内容为空")
            
    except Exception as e:
        print(f"❌ 运行报错: {e}")

if __name__ == "__main__":
    generate_report()
