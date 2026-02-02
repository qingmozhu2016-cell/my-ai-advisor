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
    🇨🇳 新浪财经实时接口 (解决 Yahoo A股延迟问题)
    格式: http://hq.sinajs.cn/list=sh000001
    """
    try:
        headers = {'Referer': 'https://finance.sina.com.cn'}
        resp = requests.get(f"http://hq.sinajs.cn/list={symbol_code}", headers=headers)
        # 返回数据格式: var hq_str_sh000001="上证指数,开,昨收,现价,高,低...";
        content = resp.text
        if "," not in content: return None
        
        data = content.split('"')[1].split(',')
        current_price = float(data[3]) # 现价
        prev_close = float(data[2])    # 昨收
        
        # 停牌或未开盘时，现价可能为0，取昨收
        if current_price == 0: current_price = prev_close
            
        change_pct = ((current_price - prev_close) / prev_close) * 100
        return current_price, change_pct
    except Exception as e:
        print(f"⚠️ 新浪接口异常 ({name}): {e}")
        return None

def get_yahoo_realtime(symbol):
    """🌍 Yahoo 实时接口 (用于美债、黄金、比特币)"""
    try:
        ticker = yf.Ticker(symbol)
        # 强制获取最新分时数据
        df = ticker.history(period="2d", interval="60m")
        if df.empty: return None
        
        price = df['Close'].iloc[-1]
        # 简单的涨跌计算逻辑
        prev = df['Close'].iloc[0] 
        change = ((price - prev) / prev) * 100
        return price, change
    except: return None

def get_market_table():
    """生成混合数据源行情表"""
    print("📊 正在同步全球行情 (Sina + Yahoo)...")
    
    # 1. 定义数据源
    # A股用新浪 (代码前加 sh/sz)
    sina_tickers = [
        ('sh000001', '🇨🇳 上证指数'),
        ('sz399006', '🇨🇳 创业板指'),
    ]
    # 全球用 Yahoo
    yahoo_tickers = {
        'CNY=X': '💱 美元/人民币', 
        'GC=F': '🟡 黄金期货',
        'BTC-USD': '🪙 比特币',
        '^TNX': '🇺🇸 10年美债'
    }

    md_table = "| 资产 | 最新价 | 涨跌幅 |\n|---|---|---|\n"

    # 2. 抓取新浪数据
    for code, name in sina_tickers:
        res = get_sina_data(code, name)
        if res:
            price, chg = res
            icon = "🔺" if chg > 0 else "💚"
            md_table += f"| {name} | {price:.2f} | {icon} {chg:+.2f}% |\n"

    # 3. 抓取 Yahoo 数据
    for symbol, name in yahoo_tickers.items():
        res = get_yahoo_realtime(symbol)
        if res:
            price, chg = res
            icon = "🔺" if chg > 0 else "💚"
            if "CNY" in symbol: fmt = f"{price:.4f}"
            elif "^" in symbol: fmt = f"{price:.3f}%"
            else: fmt = f"{price:.2f}"
            md_table += f"| {name} | {fmt} | {icon} {chg:+.2f}% |\n"
            
    return md_table

def get_news_brief():
    """获取新闻 (Top 5)"""
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
            for entry in feed.entries[:3]: # 每个源取3条，交给AI选5条
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
    """发送富文本邮件 (HTML正文 + MD附件)"""
    if not EMAIL_USER: return
    
    msg = MIMEMultipart()
    msg['Subject'] = title
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO
    
    # 1. 生成 HTML 正文 (手机适配样式)
    html_body = markdown.markdown(md_content, extensions=['tables'])
    
    # 添加 CSS 样式，让手机阅读更舒服
    html_style = """
    <html>
    <head>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 10px; }
        h1, h2, h3 { color: #2c3e50; margin-top: 20px; }
        table { border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 14px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        blockquote { border-left: 4px solid #4caf50; padding-left: 10px; color: #666; background: #f9f9f9; }
        li { margin-bottom: 5px; }
    </style>
    </head>
    <body>
    """
    full_html = f"{html_style}{html_body}</body></html>"
    msg.attach(MIMEText(full_html, 'html'))

    # 2. 添加 MD 附件
    try:
        with open(filename, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(filename))
        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(filename)}"'
        msg.attach(part)
    except Exception as e:
        print(f"附件添加失败: {e}")

    # 3. 发送
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        server.quit()
        print("✅ HTML 邮件 + 附件已发送！")
    except Exception as e:
        print(f"❌ 发送失败: {e}")

def generate_report():
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 获取数据
    market = get_market_table()
    news = get_news_brief()
    knowledge = get_obsidian_knowledge()
    
    print("🤖 Gemini 正在生成策略...")
    
    prompt = f"""
    【角色】朱文翔（资深理财经理，反脆弱践行者）。
    【日期】{date_str}
    
    【任务】撰写《家庭财富风险管理日报》。
    
    【素材】
    1. 行情（Sina实时源）：\n{market}
    2. 新闻：\n{news}
    3. 笔记：\n{knowledge}
    
    【要求】
    1. **核心看板**：展示行情表，简评A股与外部环境的背离或联动。
    2. **新闻Top 5**：精选5条对钱袋子影响最大的新闻，每条附带“影响点评”。
    3. **策略建议**：
       - 结合笔记库理论（最多引用1次），给出一个明确的操作指令（如：定投、止盈、观望）。
       - 语气要像老朋友一样真诚。
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        
        if response.text:
            # 保存文件
            if not os.path.exists(REPORT_DIR): os.makedirs(REPORT_DIR)
            filepath = f"{REPORT_DIR}/{date_str}_AI_Daily.md"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response.text)
                
            # 发送邮件 (HTML + 附件)
            send_rich_email(f"【AI内参】{date_str} 核心策略", response.text, filepath)
        else:
            print("❌ 生成内容为空")
            
    except Exception as e:
        print(f"❌ 运行报错: {e}")

if __name__ == "__main__":
    generate_report()
