import os
import glob
import yfinance as yf
import feedparser
from google import genai
from datetime import datetime
import re
import smtplib
from email.mime.multipart import MIMEMultipart  # 新增：支持多部分混合
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication # 新增：支持附件
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

# --- 2. 研报美化样式 (CSS) ---
HTML_STYLE = """
<style>
    body { font-family: "Helvetica Neue", Helvetica, "PingFang SC", "Microsoft YaHei", Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
    h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
    h2 { color: #e67e22; margin-top: 30px; border-left: 5px solid #e67e22; padding-left: 10px; }
    h3 { color: #2980b9; }
    table { border-collapse: collapse; width: 100%; margin: 20px 0; font-size: 14px; }
    th { background-color: #f2f2f2; color: #333; font-weight: bold; padding: 10px; border: 1px solid #ddd; text-align: center; }
    td { padding: 10px; border: 1px solid #ddd; text-align: center; }
    tr:nth-child(even) { background-color: #f9f9f9; }
    blockquote { border-left: 4px solid #ddd; padding-left: 15px; color: #777; font-style: italic; background: #fdfdfd; padding: 10px; }
    strong { color: #c0392b; }
    .footer { margin-top: 40px; font-size: 12px; color: #aaa; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }
</style>
"""

def get_market_data():
    """获取核心资产数据"""
    print("📊 正在获取行情...")
    tickers = {
        '000001.SS': '🇨🇳 上证指数',
        '399006.SZ': '🇨🇳 创业板指',
        'CNY=X': '💱 美元/人民币', 
        'FXI': '🇨🇳 A50 (ETF)',
        '^TNX': '🇺🇸 10年美债',
        'GC=F': '🟡 黄金期货',
        'BTC-USD': '🪙 比特币'
    }
    try:
        data = yf.download(list(tickers.keys()), period="5d", progress=False)
        df = data['Close'] if 'Close' in data else data
        
        md_table = "| 资产 | 日期 | 最新价 | 涨跌 |\n|---|---|---|---|\n"
        for symbol, name in tickers.items():
            try:
                series = df[symbol].dropna()
                if series.empty: continue
                
                last_date = series.index[-1]
                price = series.iloc[-1]
                prev = series.iloc[-2] if len(series) > 1 else price
                
                date_str = last_date.strftime('%m-%d')
                today_str = datetime.now().strftime('%m-%d')
                date_display = f"**{date_str}**" if date_str == today_str else f"{date_str}"

                pct_change = ((price - prev) / prev) * 100
                icon = "🔺" if pct_change > 0 else "💚"
                
                if "CNY" in symbol: fmt = f"{price:.4f}"
                elif "^" in symbol: fmt = f"{price:.3f}%"
                else: fmt = f"{price:.2f}"
                
                md_table += f"| {name} | {date_display} | {fmt} | {icon} {pct_change:+.2f}% |\n"
            except: pass
        return md_table
    except: return "*(行情数据不可用)*"

def get_news_brief():
    """获取 Top 5 新闻"""
    print("🌍 正在筛选新闻...")
    news_list = []
    sources = [
        {"name": "联合早报", "url": "https://www.zaobao.com.sg/rss/finance.xml"},
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"}
    ]
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            for entry in feed.entries[:5]:
                clean_summary = re.sub('<.*?>', '', getattr(entry, 'summary', '')).strip()
                news_list.append(f"【{src['name']}】{entry.title} - {clean_summary[:100]}")
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
    """
    保存 Markdown 文件 + 发送带附件的 HTML 邮件
    """
    # 1. 保存 Markdown 文件 (给 Obsidian 用)
    if not os.path.exists(REPORT_DIR):
        os.makedirs(REPORT_DIR)
    
    filename = f"{REPORT_DIR}/{datetime.now().strftime('%Y-%m-%d')}_AI_Daily.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    print(f"✅ MD文件已保存: {filename}")

    # 2. 准备发送邮件
    if not EMAIL_USER: return

    # 创建一个带附件的邮件对象
    msg = MIMEMultipart()
    msg['Subject'] = title
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO

    # --- Part A: 邮件正文 (HTML) ---
    html_body = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])
    full_html = f"""
    <html>
    <head>{HTML_STYLE}</head>
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

    # --- Part B: 邮件附件 (.md 文件) ---
    try:
        with open(filename, "rb") as f:
            # 读取文件内容作为附件
            part = MIMEApplication(f.read(), Name=os.path.basename(filename))
        
        # 设置附件头信息
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(filename)}"'
        msg.attach(part)
        print("📎 附件添加成功")
    except Exception as e:
        print(f"⚠️ 附件添加失败: {e}")

    # --- 发送 ---
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ 邮件(含附件)已发送！")
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
    (筛选5条对中国家庭影响最大的新闻。格式：`1. **标题**：点评`)
    
    **三、深度策略 (引用笔记)**
    (结合新闻和反脆弱笔记，给出一项具体操作建议)
    """
    
    try:
        response = client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
        
        if response.text:
            save_and_send(f"【AI日报】{date_str} 精选策略 (含附件)", response.text)
        else:
            print("❌ 内容为空")
            
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    generate_report()
