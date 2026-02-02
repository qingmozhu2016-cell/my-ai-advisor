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

# --- 1. 基础配置 (云端安全版) ---
# 自动清洗密钥中的空格/换行符，防止报错
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
client = genai.Client(api_key=API_KEY)

# Gmail 配置
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = os.environ.get("EMAIL_USER", "").strip()
EMAIL_PASS = os.environ.get("EMAIL_PASS", "").strip()
EMAIL_TO = os.environ.get("EMAIL_TO", "").strip()

# 知识库路径
OBSIDIAN_PATH = "./knowledge_base"

def get_china_market_data():
    """
    📊 获取核心资产行情 (去伪存真版)
    逻辑：强制剔除空值，确保取到最新有效收盘价
    """
    print("📊 正在同步核心资产行情...")
    # 核心资产池：上证、创业板、离岸人民币、A50(代理)、美债、黄金
    tickers = {
        '000001.SS': '🇨🇳 上证指数',
        '399006.SZ': '🇨🇳 创业板指',
        'CNY=X': '💱 美元/人民币', 
        'FXI': '🇨🇳 中国A50 (ETF代理)', 
        '^TNX': '🇺🇸 10年美债',
        'GC=F': '🟡 黄金期货'
    }
    
    try:
        # 抓取过去 7 天数据，以防长假缺口
        data = yf.download(list(tickers.keys()), period="7d", progress=False)
        # 兼容不同 yfinance 版本的返回格式
        df = data['Close'] if 'Close' in data else data

        md_table = "| 核心资产 | 最新报价 | 趋势 |\n|---|---|---|\n"
        
        for symbol, name in tickers.items():
            try:
                # 核心逻辑：.dropna() 剔除所有空值行
                series = df[symbol].dropna()
                
                if series.empty:
                    md_table += f"| {name} | 数据缺失 | - |\n"
                    continue
                
                # 取最后一天（最新）和倒数第二天（前一日）
                price = series.iloc[-1]
                prev = series.iloc[-2] if len(series) > 1 else price
                
                # 计算涨跌
                change = price - prev
                icon = "🔺" if change > 0 else "💚"
                
                # 格式化输出
                if "CNY" in symbol: fmt = f"{price:.4f}"
                elif "^" in symbol: fmt = f"{price:.3f}%"
                else: fmt = f"{price:.2f}"
                
                md_table += f"| {name} | {fmt} | {icon} |\n"
            except Exception as e:
                print(f"   ⚠️ {name} 数据处理微瑕: {e}")
                
        return md_table
    except Exception as e:
        return f"*(行情接口暂时波动: {str(e)})*"

def get_news_brief():
    """
    🌍 获取新闻 (中西合璧版)
    源1: Yahoo Finance (国际视角的英文原声)
    源2: 联合早报/FT中文 (华人视角的中文原声)
    """
    print("🌍 正在聚合双语财经新闻...")
    news_content = ""
    
    sources = [
        {"name": "Yahoo Finance (国际)", "url": "https://finance.yahoo.com/news/rssindex"},
        {"name": "联合早报 (财经)", "url": "https://www.zaobao.com.sg/rss/finance.xml"}
    ]
    
    for src in sources:
        try:
            feed = feedparser.parse(src["url"])
            if not feed.entries: continue
            
            news_content += f"\n**【{src['name']}】**\n"
            # 每个源只取前 3 条，避免过长
            for i, entry in enumerate(feed.entries[:3], 1):
                clean_summary = re.sub('<.*?>', '', getattr(entry, 'summary', '')).strip()
                news_content += f"{i}. {entry.title}\n   摘要: {clean_summary[:100]}...\n"
        except:
            news_content += f"\n*({src['name']} 连接超时)*\n"
            
    return news_content

def get_obsidian_knowledge():
    """读取私人笔记"""
    print("🧠 正在加载知识库...")
    context = ""
    if os.path.exists(OBSIDIAN_PATH):
        files = glob.glob(os.path.join(OBSIDIAN_PATH, "*.md"))
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    context += f"\n【参考笔记：{os.path.basename(f)}】\n{file.read()[:2000]}\n"
            except: pass
    else:
        context = "*(未检测到知识库文件)*"
    return context

def send_gmail(subject, content):
    """防封锁 Gmail 发送函数"""
    if not EMAIL_USER or "@" not in EMAIL_USER:
        print("❌ 邮箱配置为空，跳过发送")
        return

    msg = MIMEText(content, 'markdown', 'utf-8') # 尝试用 Markdown 格式
    msg['Subject'] = subject
    msg['From'] = formataddr(("朱文翔的AI助理", EMAIL_USER))
    msg['To'] = EMAIL_TO

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
    
    # 1. 获取三大核心素材
    market = get_china_market_data()
    news = get_news_brief()
    knowledge = get_obsidian_knowledge()
    
    print("🤖 Gemini 正在以理财专家的身份思考...")
    
    prompt = f"""
    【角色设定】
    你叫朱文翔，一名拥有多年经验的资深保险销售员和理财经理。你的客户群体是关注家庭财富安全的中产家庭。你的投资哲学深受纳西姆·塔勒布的“反脆弱”理论和达利欧的“全天候”策略影响。
    
    【今日日期】：{date_str}
    
    【输入素材】
    1. 核心行情（已清洗）：
    {market}
    
    2. 全球新闻（中西合璧）：
    {news}
    
    3. 你的私人知识库（Obsidian）：
    {knowledge}
    
    【任务要求】
    请为你的客户写一份《家庭财富风险管理日报》。要求如下：
    
    1. **宏观定调（中国本位）**：
       - 先看【行情】中的人民币汇率和中国资产表现，判断国内情绪。
       - 再结合【新闻】中的外部信息（如美债、地缘政治），分析其对中国家庭财富的潜在冲击。
       
    2. **去伪存真**：
       - 不要罗列新闻，而是从繁杂的信息中提炼出 1-2 条真正影响“钱袋子”的关键信息进行点评。
       
    3. **反脆弱建议（知行合一）**：
       - **必须引用**：在给出建议时，显式引用【私人知识库】中的一句话或一个观点（例如：“正如我在笔记中所记……”），来佐证你的建议。
       - **行动指南**：给出一个具体的行动建议（例如：增配黄金、检查保险缺口、或静观其变）。
    
    【输出格式】
    - 使用 Markdown 格式。
    - 语气专业、诚恳、有温度（像是在给老客户写信）。
    - 字数控制在 600-800 字。
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        send_gmail(f"【内参】家庭财富日报 ({date_str})", response.text)
    except Exception as e:
        print(f"❌ 生成报告失败: {e}")

if __name__ == "__main__":
    generate_report()
