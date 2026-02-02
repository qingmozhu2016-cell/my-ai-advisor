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
    🇨🇳 新浪财经实时接口 (A股 + 黄金)
    格式统一，速度最快。
    """
    try:
        headers = {'Referer': 'https://finance.sina.com.cn'}
        resp = requests.get(f"http://hq.sinajs.cn/list={symbol_code}", headers=headers)
        content = resp.text
        if "," not in content: return None
        
        data = content.split('"')[1].split(',')
        current_price = float(data[3]) # 现价
        prev_close = float(data[2])    # 昨收
        
        # 停牌或集合竞价期间防错
        if current_price == 0: current_price = prev_close
            
        change_pct = ((current_price - prev_close) / prev_close) * 100
        return current_price, change_pct
    except Exception as e:
        print(f"⚠️ 新浪接口异常 ({name}): {e}")
        return None

def get_yahoo_realtime(symbol):
    """🌍 Yahoo 实时接口 (美债、比特币)"""
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
    """生成混合行情表 (黄金已切换至人民币计价)"""
    print("📊 正在同步行情 (黄金已切换至 Sina)...")
    
    # 1. 新浪源 (A股 + 黄金ETF)
    # sh518880 是国内主流的黄金ETF，完美代表人民币金价
    sina_tickers = [
        ('sh000001', '🇨🇳 上证指数'),
        ('sz399006', '🇨🇳 创业板指'),
        ('sh518880', '🟡 黄金ETF(人民币)') 
    ]
    
    # 2. Yahoo源 (外围)
    yahoo_tickers = {
        'CNY=X': '💱 美元/人民币', 
        'BTC-USD': '🪙 比特币',
        '^TNX': '🇺🇸 10年美债'
    }

    md_table = "| 资产 | 最新价 | 涨跌幅 |\n|---|---|---|\n"

    # 抓取新浪
    for code, name in sina_tickers:
        res = get_sina_data(code, name)
        if res:
            price, chg = res
            icon = "🔺" if chg > 0 else "💚"
            md_table += f"| {name} | {price:.3f} | {icon} {chg:+.2f}% |\n"

    # 抓取 Yahoo
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
    """
    发送精致排版的 HTML 邮件
    优化点：增加段间距，优化字体，适配手机
    """
    if not EMAIL_USER: return
    
    msg = MIMEMultipart()
    msg['Subject'] = title
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO
    
    # MD 转 HTML
    html_body = markdown.markdown(md_content, extensions=['tables'])
    
    # --- CSS 核心美化区 ---
    html_style = """
    <html>
    <head>
    <style>
        /* 全局适配手机 */
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif; 
            line-height: 1.8; /* 增大行高 */
            color: #333; 
            max-width: 600px; /* 限制宽度，手机看更舒服 */
            margin: 0 auto; 
            padding: 15px;
            background-color: #fcfcfc;
        }
        
        /* 标题美化 */
        h1 { font-size: 22px; color: #1a1a1a; margin-top: 25px; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        h2 { font-size: 18px; color: #2c3e50; margin-top: 30px; border-left: 4px solid #d35400; padding-left: 10px; }
        h3 { font-size: 16px; color: #555; margin-top: 20px; font-weight: bold; }
        
        /* 段落优化：拒绝长文 */
        p { margin-bottom: 18px; text-align: justify; }
        li { margin-bottom: 10px; }
        
        /* 表格美化 */
        table { border-collapse: collapse; width: 100%; margin: 20px 0; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        th { background-color: #f8f9fa; color: #666; font-weight: 600; padding: 12px 8px; font-size: 13px; text-align: center; }
        td { border-bottom: 1px solid #eee; padding: 12px 8px; font-size: 14px; text-align: center; color: #333; }
        
        /* 引用块美化 */
        blockquote { 
            background: #eef9f0; 
            border-left: 4px solid #4caf50; 
            margin: 20px 0; 
            padding: 15px; 
            color: #2e7d32; 
            font-style: italic;
            border-radius: 4px;
        }
        
        /* 重点强调 */
        strong { color: #d35400; }
    </style>
    </head>
    <body>
    """
    full_html = f"{html_style}{html_body}</body></html>"
    msg.attach(MIMEText(full_html, 'html'))

    # 添加附件
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
    
    # 重新设计的 Prompt，强调排版
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
       - 第一行：# 家庭财富风险管理日报
       - 第二行：**朱文翔（资深投资顾问，反脆弱践行者）**
       - 第三行：{date_str}
       - (注意：不要写“执笔人”三个字，直接写名字)
    
    2. **正文可读性**：
       - **禁止长难句**：每个段落不超过 3 行。
       - **多用列表**：分析新闻时，请使用无序列表（- 点评...）。
       - **留白**：板块之间保持清晰的间隔。
    
    【内容结构】
    
    **第一部分：核心资产看板**
    - 展示行情表（注意黄金现在是人民币计价）。
    - 用 2-3 个短句简评今日 A 股与黄金的表现。
    
    **第二部分：关键信号（Top 5）**
    - 筛选 5 条最重要新闻。
    - 每条新闻后，换行用 `> 💡 影响：...` 的格式简短点评。
    
    **第三部分：行动指南**
    - 结合笔记库（最多引用1次），给出一个清晰的指令。
    - 结尾语要温暖、坚定。
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
