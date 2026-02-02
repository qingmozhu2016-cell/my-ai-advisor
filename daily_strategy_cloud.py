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
HTML_STYLE = """
<style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        line-height: 1.6;
        color: #333;
        margin: 0 auto;
        padding: 10px 15px;
        max-width: 600px;
        font-size: 16px;
    }
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
        background-color: #fff8f0;
        padding: 5px 10px;
    }
    h3 { font-size: 17px; color: #2980b9; margin-top: 20px; }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        font-size: 13px;
    }
    th {
        background-color: #f4f6f7;
        color: #333;
        font-weight: bold;
        padding: 8px 4px;
        border: 1px solid #e1e4e8;
        text-align: center;
        white-space: nowrap;
    }
    td {
        padding: 8px 4px;
        border: 1px solid #e1e4e8;
        text-align: center;
    }
    tr:nth-child(even) { background-color: #fbfbfc; }
    blockquote {
        border-left: 3px solid #ccc;
        margin: 15px 0;
        padding: 8px 12px;
        color: #555;
        background: #f9f9f9;
        font-size: 15px;
    }
    strong { color: #c0392b; font-weight: 600; }
    .footer {
        margin-top: 30px;
        font-size: 12px;
        color: #999;
        text-align: center;
        border-top: 1px dashed #ddd;
        padding-top: 15px;
    }
    @media screen and (max-width: 400px) {
        body { padding: 8px; }
        h1 { font-size: 20px; }
        table { font-size: 12px; }
    }
</style>
"""

def get_market_data():
    """获取核心资产数据"""
    print("📊 正在获取行情...")
    tickers = {
        '000001.SS': '🇨🇳 上证',
        '399006.SZ': '🇨🇳 创业板',
        'CNY=X': '💱 汇率', 
        'FXI': '🇨🇳 A50',
        '^TNX': '🇺🇸 美债',
        'GC=F': '🟡 黄金',
        'BTC-USD': '🪙 BTC'
    }
    
    # ⚠️ 修正缩进逻辑：将 try 块完整包裹
    try:
        data = yf.download(list(tickers.keys()), period="5d", progress=False)
        
        # 稳健写法：避免单行 if-else 造成的缩进歧义
        if 'Close' in data:
            df = data['Close']
        else:
            df = data
        
        md_table = "| 资产 | 日期 | 最新 | 涨跌 |\n|---|---|---|---|\n"
        
        for symbol, name in tickers.items():
            try:
                series = df[symbol].dropna()
                if series.empty: continue
                
                last_date = series.index[-1]
                price = series.iloc[-1]
                prev = series.iloc[-2] if len(series) > 1 else price
                
                date_str = last_date.strftime('%m-%d')
                today_str = datetime.now().strftime('%m-%d')
                
                if date_str == today_str:
                    date_display = f"**{date_str}**"
                else:
                    date_display = f"{date_str}"

                pct_change = ((price - prev) / prev) * 100
                icon = "🔺" if pct_change > 0 else "💚"
                
                if "CNY" in symbol: fmt = f"{price:.4f}"
                elif "^" in symbol: fmt = f"{price:.2f}%"
                else: fmt = f"{price:.0f}"
                
                md_table += f"| {name} | {date_display} | {fmt} | {icon}{pct_change:+.1f}% |\n"
            except: 
                pass
                
        return md_table
        
    except Exception as e:
        return f"*(行情数据不可用: {str(e)})*"

def get_news_brief():
    """获取 Top 5 新闻"""
    print("🌍 正在筛选新闻...")
    news_list = []
    sources = [
        {"name": "早报", "url": "https://www.zaobao.com.sg/rss/finance.xml"},
        {"name": "Yahoo", "url": "https://finance.yahoo.com/news/rssindex"}
    ]
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            for entry in feed.entries[:5]:
                clean_summary = re.sub('<.*?>', '', getattr(entry, 'summary', '')).strip()
                news_list.append(f"【{src['name']}】{entry.title} - {clean_summary[:80]}")
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

def save_and_send(title, markdown_content):
    """保存并发送 (带附件 + 移动端适配)"""
    if not os.path.exists(REPORT_DIR):
        os.makedirs(REPORT_DIR)
    
    filename = f"{REPORT_DIR}/{datetime.now().strftime('%Y-%m-%d')}_AI_Daily.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    print(f"✅ MD文件已保存: {filename}")

    if not EMAIL_USER: return

    msg = MIMEMultipart()
    msg['Subject'] = title
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO

    html_body = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])
    
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {HTML_STYLE}
    </head>
    <body>
        {html_body}
        <div class="footer">
            <p>Generated by Gemini 2.5 Pro | 朱文翔的 AI 助理</p>
            <p>附件为 Markdown 原始文档，可直接导入 Obsidian</p>
        </div>
    </body>
    </html>
    """
    msg.attach(MIMEText(full_html, 'html', 'utf-8'))

    try:
        with open(filename, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(filename))
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(filename)}"'
        msg.attach(part)
    except Exception as e:
        print(f"⚠️ 附件添加失败: {e}")

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ 邮件(移动端优化版)已发送！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    market = get_market_data()
    news = get_news_brief()
    knowledge = get_obsidian_knowledge()
    
    print("🤖 Gemini 2.5 Pro 正在生成...")
    
    prompt = f"""
    【角色】朱文翔（资深理财经理）。
    【日期】{date_str}
    
    【任务】生成《家庭财富风险管理日报》，Markdown格式。
    
    【素材】
    1. 行情：\n{market}
    2. 新闻池：\n{news}
    3. 笔记：\n{knowledge}
    
    【结构要求】
    **一、核心资产看板**
    (展示行情表格，点评BTC/黄金)
    
    **二、财经要闻速递 (Top 5)**
    (筛选5条核心新闻。格式：`1. **标题**：点评`)
    
    **三、深度策略 (引用笔记)**
    (结合新闻和反脆弱笔记，给出一项具体操作建议)
    """
    
    try:
        response = client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
        if response.text:
            save_and_send(f"【AI日报】{date_str} 精选策略", response.text)
        else:
            print("❌ 内容为空")
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    generate_report()
