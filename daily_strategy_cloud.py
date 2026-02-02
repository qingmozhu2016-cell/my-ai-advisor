import os
import glob
import yfinance as yf
import feedparser
import requests
import markdown
from google import genai
from datetime import datetime
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr

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

def get_sina_data(symbol_code, name):
    """
    🇨🇳 新浪财经实时接口
    """
    try:
        headers = {'Referer': 'https://finance.sina.com.cn'}
        resp = requests.get(f"http://hq.sinajs.cn/list={symbol_code}", headers=headers)
        content = resp.text
        if "," not in content: return None
        
        data = content.split('"')[1].split(',')
        current_price = float(data[3])
        prev_close = float(data[2])
        if current_price == 0: current_price = prev_close
            
        change_pct = ((current_price - prev_close) / prev_close) * 100
        return current_price, change_pct
    except Exception as e:
        print(f"⚠️ 新浪接口异常 ({name}): {e}")
        return None

def get_yahoo_realtime(symbol):
    """🌍 Yahoo 实时接口"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2d", interval="60m")
        if df.empty: return None
        price = df['Close'].iloc[-1]
        prev = df['Close'].iloc[0] 
        change = ((price - prev) / prev) * 100
        return price, change
    except: return None

def get_market_table():
    """生成混合行情表 (含特殊单位处理)"""
    print("📊 正在同步行情 (黄金折算 + BTC美元)...")
    
    sina_tickers = [
        ('sh000001', '🇨🇳 上证指数'),
        ('sz399006', '🇨🇳 创业板指'),
        ('sh518880', '🟡 黄金价格(CNY)') 
    ]
    
    yahoo_tickers = {
        'CNY=X': '💱 美元/人民币', 
        'BTC-USD': '🪙 比特币',
        '^TNX': '🇺🇸 10年美债'
    }

    md_table = "| 资产 | 最新价 | 涨跌幅 |\n|---|---|---|\n"

    # 1. 处理新浪数据 (特殊处理黄金)
    for code, name in sina_tickers:
        res = get_sina_data(code, name)
        if res:
            price, chg = res
            icon = "🔺" if chg > 0 else "💚"
            
            # 💡 核心修改：黄金 ETF 价格 * 100 = 元/克
            if "518880" in code:
                real_gold_price = price * 100
                fmt_price = f"{real_gold_price:.2f} 元/克"
            else:
                fmt_price = f"{price:.2f}"
            
            md_table += f"| {name} | {fmt_price} | {icon} {chg:+.2f}% |\n"

    # 2. 处理 Yahoo 数据 (特殊处理比特币)
    for symbol, name in yahoo_tickers.items():
        res = get_yahoo_realtime(symbol)
        if res:
            price, chg = res
            icon = "🔺" if chg > 0 else "💚"
            
            # 💡 核心修改：比特币加 $ 符号
            if "BTC" in symbol: 
                fmt = f"$ {price:,.2f}" # 加逗号分隔千分位
            elif "CNY" in symbol: 
                fmt = f"{price:.4f}"
            elif "^" in symbol: 
                fmt = f"{price:.3f}%"
            else: 
                fmt = f"{price:.2f}"
                
            md_table += f"| {name} | {fmt} | {icon} {chg:+.2f}% |\n"
            
    return md_table

def get_news_brief():
    """获取新闻"""
    print("🌍 正在聚合新闻...")
    news_list = []
    sources = [
        {"name": "联合早报", "url": "https://www.zaobao.com.sg/rss/finance.xml"},
        {"name": "Yahoo", "url": "https://finance.yahoo.com/news/rssindex"}
    ]
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            for entry in feed.entries[:3]: 
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

def send_rich_email(title, md_content, filename):
    """发送 HTML 邮件"""
    if not EMAIL_USER: return
    
    msg = MIMEMultipart()
    msg['Subject'] = title
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO
    
    html_body = markdown.markdown(md_content, extensions=['tables'])
    
    html_style = """
    <html>
    <head>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 15px; }
        h1 { font-size: 20px; color: #111; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-top: 20px; }
        h2 { font-size: 18px; color: #0056b3; margin-top: 30px; margin-bottom: 15px; border-left: 4px solid #0056b3; padding-left: 10px; }
        h3 { font-size: 16px; font-weight: bold; margin-top: 20px; color: #444; }
        p { margin-bottom: 15px; text-align: justify; }
        ul { padding-left: 20px; margin-bottom: 20px; }
        li { margin-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }
        th, td { border: 1px solid #e1e4e8; padding: 8px 10px; text-align: center; }
        th { background-color: #f6f8fa; }
        blockquote { border-left: 4px solid #28a745; background: #f0fff4; padding: 10px 15px; margin: 15px 0; color: #2c662d; border-radius: 4px; }
        strong { color: #d73a49; }
    </style>
    </head>
    <body>
    """
    full_html = f"{html_style}{html_body}</body></html>"
    msg.attach(MIMEText(full_html, 'html'))

    try:
        with open(filename, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(filename))
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(filename)}"'
        msg.attach(part)
    except: pass

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ 邮件已发送！")
    except Exception as e:
        print(f"❌ 发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    market = get_market_table()
    news = get_news_brief()
    knowledge = get_obsidian_knowledge()
    
    print("🤖 Gemini 正在生成策略...")
    
    prompt = f"""
    【角色设定】
    你叫朱文翔（资深投资顾问，反脆弱践行者）。
    
    【任务】
    生成一份《家庭财富风险管理日报》，Markdown格式。
    
    【输入素材】
    1. 行情：\n{market}
    2. 新闻：\n{news}
    3. 笔记：\n{knowledge}
    
    【排版严格要求】
    1. **头部格式**：
       - # 家庭财富风险管理日报
       - **朱文翔（资深投资顾问，反脆弱践行者）**
       - {date_str}
    
    2. **第三部分特别要求（强制分段）**：
       - 指令和建议必须清晰分开，**绝对不要**写成一大段。
       - 请严格按以下格式输出第三部分：
         ### 行动指南
         **【核心指令】**
         (此处写指令，如：买入/持有/观望)
         
         **【逻辑支撑】**
         (此处写分析逻辑，分段写)
         
         **【笔记共鸣】**
         (如有引用，写在这里；如无引用，写心得)
    
    【内容结构】
    
    **第一部分：核心资产看板**
    - 展示表格。
    - 简评A股与黄金（注意黄金已折算为元/克）。
    
    **第二部分：关键信号（Top 5）**
    - 筛选 5 条新闻。
    - 格式：`1. [标题]` -> 换行 -> `> 💡 影响：...`
    
    **第三部分：行动指南**
    - 按上述要求的“强制分段格式”输出。
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        
        if response.text:
            if not os.path.exists(REPORT_DIR): os.makedirs(REPORT_DIR)
            filepath = f"{REPORT_DIR}/{date_str}_AI_Daily.md"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response.text)
            
            send_rich_email(f"【内参】{date_str} 核心策略", response.text, filepath)
        else:
            print("❌ 生成内容为空")
            
    except Exception as e:
        print(f"❌ 运行报错: {e}")

if __name__ == "__main__":
    generate_report()
