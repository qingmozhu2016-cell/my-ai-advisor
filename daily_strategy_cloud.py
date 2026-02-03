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
    """生成混合行情表"""
    print("📊 正在同步行情...")
    
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

    for code, name in sina_tickers:
        res = get_sina_data(code, name)
        if res:
            price, chg = res
            icon = "🔺" if chg > 0 else "💚"
            if "518880" in code:
                real_gold_price = price * 100
                fmt_price = f"{real_gold_price:.2f} 元/克"
            else:
                fmt_price = f"{price:.2f}"
            md_table += f"| {name} | {fmt_price} | {icon} {chg:+.2f}% |\n"

    for symbol, name in yahoo_tickers.items():
        res = get_yahoo_realtime(symbol)
        if res:
            price, chg = res
            icon = "🔺" if chg > 0 else "💚"
            if "BTC" in symbol: 
                fmt = f"$ {price:,.2f}"
            elif "CNY" in symbol: 
                fmt = f"{price:.4f}"
            elif "^" in symbol: 
                fmt = f"{price:.3f}%"
            else: 
                fmt = f"{price:.2f}"
            md_table += f"| {name} | {fmt} | {icon} {chg:+.2f}% |\n"
            
    return md_table

def get_news_brief():
    """获取新闻 (加大国内新闻抓取量)"""
    print("🌍 正在聚合新闻...")
    news_list = []
    sources = [
        # 新浪源抓取量增加到 6 条，确保有足够的国内素材供筛选
        {"name": "新浪财经", "url": "http://rss.sina.com.cn/roll/finance/hot_roll.xml", "count": 6},
        {"name": "联合早报", "url": "https://www.zaobao.com.sg/rss/finance.xml", "count": 3},
        {"name": "Yahoo", "url": "https://finance.yahoo.com/news/rssindex", "count": 3}
    ]
    
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            limit = src.get("count", 3)
            for entry in feed.entries[:limit]: 
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
        body { font-family: -apple-system, system-ui, "Microsoft YaHei", sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 15px; }
        h1 { font-size: 20px; color: #111; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-top: 20px; }
        h2 { font-size: 18px; color: #b71c1c; margin-top: 35px; margin-bottom: 15px; border-left: 4px solid #b71c1c; padding-left: 10px; }
        h3 { font-size: 16px; font-weight: bold; margin-top: 25px; color: #0d47a1; }
        p { margin-bottom: 15px; text-align: justify; font-size: 15px; }
        ul { padding-left: 20px; margin-bottom: 20px; }
        li { margin-bottom: 10px; }
        
        /* 表格样式增强 */
        table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-radius: 4px; overflow: hidden; }
        th, td { border: 1px solid #e1e4e8; padding: 8px 5px; text-align: center; }
        th { background-color: #f6f8fa; color: #333; font-weight: bold; }
        /* 让配置表的最后一列稍微宽一点 */
        td:last-child { text-align: left; padding-left: 10px; color: #555; }
        
        blockquote { border-left: 4px solid #f9a825; background: #fffde7; padding: 15px; margin: 20px 0; color: #555; border-radius: 6px; font-style: italic;}
        strong { color: #d32f2f; }
        .footer { font-size: 12px; color: #999; margin-top: 40px; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }
    </style>
    </head>
    <body>
    """
    full_html = f"{html_style}{html_body}<div class='footer'>本报告由 AI 辅助生成，仅供参考，不构成投资建议。</div></body></html>"
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
    
    print("🤖 Gemini 正在构思历史故事与全天候策略...")
    
    prompt = f"""
    【角色设定】
    你叫朱文翔，一名资深、稳健的投资顾问。
    你的读者是**有一定资产、但风险偏好较低的保险意向客户**。
    
    【核心理念】
    你信奉**全天候策略 (All-Weather)** 和 **反脆弱**，强调利用保险和固收资产作为家庭财富的“压舱石”。

    【日期】{date_str}

    【素材】
    1. 行情：\n{market}
    2. 新闻池（请从中筛选）：\n{news}
    3. 笔记：\n{knowledge}

    【任务】撰写《家庭财富风险管理日报》。

    【文章结构要求】

    **第一部分：核心资产看板**
    - 展示表格。
    - 用“大白话”简评市场。

    **第二部分：财经要闻（Top 5）**
    - 筛选 5 条最重要新闻。
    - **强制要求：其中必须至少包含 1 条中国国内的重要宏观或政策新闻**（从新浪源中选取）。
    - **强制中文标题**。
    - 格式：`1. [标题]` -> `[一句话事实]` -> `> 💡 对家庭财富的影响：...`

    **第三部分：历史映照与行动指南**
    
    1. **【今日锚点】**：
       - 挑一个热点话题。
    
    2. **【历史回响】(讲故事)**：
       - 找一个**历史经典案例**（如大萧条、郁金香泡沫、历次降息周期等）来映射今天的新闻。
       - 目的：告诉客户“太阳底下无新鲜事”，长期主义能战胜波动。
    
    3. **【给您的建议】(展示配置表)**：
       - 结合今日行情，给出一个简短的建议（如：保持定力，检查现金流）。
       - **必须展示**一张《家庭资产全天候配置参考表》（Markdown表格形式）。
       - **表格要求**：根据今天的市场环境（比如是进攻期还是防御期），微调以下比例，但总体要符合“全天候”逻辑。
       - **参考格式**：
         | 资产角色 | 建议比例 | 典型标的 | 作用 |
         | :--- | :--- | :--- | :--- |
         | **进攻矛** | 20-30% | 优质股票/权益基金 | 博取长期超额收益 |
         | **防御盾** | 40-50% | **年金险/增额寿/国债** | **锁定利率，家庭兜底** |
         | **避风港** | 10-20% | 黄金/硬通货 | 对冲极端风险 |
         | **现金流** | 10% | 货币基金/活期 | 随时应急 |
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
            
            send_rich_email(f"【内参】{date_str} 历史映照与配置建议", response.text, filepath)
        else:
            print("❌ 生成内容为空")
            
    except Exception as e:
        print(f"❌ 运行报错: {e}")

if __name__ == "__main__":
    generate_report()
