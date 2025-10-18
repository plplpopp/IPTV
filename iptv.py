import requests
import pandas as pd
import re
import os
import time
import concurrent.futures
from urllib.parse import urlparse
from tqdm import tqdm
import sys

# ============================ 配置文件 ============================
# 源URL列表 - 已更新为新的源地址
URL_SOURCES = [
    "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
    "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",  
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
    "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
    "http://47.120.41.246:8899/zb.txt",
]

# 本地源文件
LOCAL_SOURCE_FILE = "local.txt"

# 模板频道文件
TEMPLATE_FILE = "demo.txt"

# 输出文件
OUTPUT_TXT = "iptv.txt"
OUTPUT_M3U = "iptv.m3u"

# 每个频道保留的接口数量
MAX_STREAMS_PER_CHANNEL = 8

# 请求超时时间（秒）
REQUEST_TIMEOUT = 3

# 最大线程数
MAX_WORKERS = 10

# ============================ 正则表达式 ============================
# IPv4地址匹配
ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')

# 频道名称和URL匹配
channel_pattern = re.compile(r"^([^,]+?),\s*(https?://.+)", re.IGNORECASE)

# M3U格式解析
extinf_pattern = re.compile(r'tvg-name="([^"]*)"', re.IGNORECASE)
extinf_name_pattern = re.compile(r'#EXTINF:.*?,(.+)', re.IGNORECASE)

def create_test_files():
    """创建测试文件用于完整性测试"""
    print("创建测试文件...")
    
    # 创建模板文件
    template_content = """央视频道,#genre#
CCTV-1综合,http://example.com/cctv1
CCTV-2财经,http://example.com/cctv2
CCTV-5体育,http://example.com/cctv5
CCTV-13新闻,http://example.com/cctv13
卫视频道,#genre#
湖南卫视,http://example.com/hunan
浙江卫视,http://example.com/zhejiang
东方卫视,http://example.com/dongfang
北京卫视,http://example.com/beijing
江苏卫视,http://example.com/jiangsu"""
    
    try:
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            f.write(template_content)
        print(f"✅ 创建模板文件: {TEMPLATE_FILE}")
    except Exception as e:
        print(f"❌ 创建模板文件失败: {e}")
        return False
    
    # 创建本地源文件
    local_content = """CCTV-1综合,http://192.168.1.100/cctv1
CCTV-2财经,http://192.168.1.100/cctv2
湖南卫视,http://192.168.1.100/hunan
浙江卫视,http://192.168.1.100/zhejiang
CCTV-1综合,http://10.0.0.100/cctv1
测试频道,http://example.com/test"""
    
    try:
        with open(LOCAL_SOURCE_FILE, 'w', encoding='utf-8') as f:
            f.write(local_content)
        print(f"✅ 创建本地源文件: {LOCAL_SOURCE_FILE}")
    except Exception as e:
        print(f"❌ 创建本地源文件失败: {e}")
        return False
    
    return True

def load_template_channels():
    """
    加载模板频道列表
    返回: 频道名称列表，保持模板中的顺序，包含分类行
    """
    if not os.path.exists(TEMPLATE_FILE):
        print(f"❌ 模板文件 {TEMPLATE_FILE} 不存在")
        if not create_test_files():
            return []
    
    template_channels = []
    try:
        print(f"📁 正在加载模板文件: {TEMPLATE_FILE}")
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    template_channels.append(line)
        print(f"✅ 模板文件加载完成，共 {len(template_channels)} 行")
        
        # 验证模板格式
        actual_channels = [line for line in template_channels if '#genre#' not in line and ',' in line]
        if not actual_channels:
            print("⚠️  警告: 模板文件中没有找到有效的频道行")
        
    except Exception as e:
        print(f"❌ 加载模板文件失败: {e}")
        return []
    
    return template_channels

def load_local_sources():
    """
    加载本地源文件
    返回: 流数据行列表
    """
    local_streams = []
    if not os.path.exists(LOCAL_SOURCE_FILE):
        print(f"⚠️  本地源文件 {LOCAL_SOURCE_FILE} 不存在，跳过")
        return local_streams
    
    try:
        print(f"📁 正在加载本地源文件: {LOCAL_SOURCE_FILE}")
        with open(LOCAL_SOURCE_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    local_streams.append(line)
        print(f"✅ 本地源文件加载完成，共 {len(local_streams)} 个流")
    except Exception as e:
        print(f"❌ 加载本地源文件失败: {e}")
    
    return local_streams

def fetch_online_sources():
    """
    抓取在线源数据
    返回: 流数据列表
    """
    online_streams = []
    
    def fetch_single_url(url):
        """获取单个URL的源数据"""
        try:
            print(f"🌐 正在抓取: {url}")
            response = requests.get(url, timeout=15, verify=False)
            response.encoding = 'utf-8'
            if response.status_code == 200:
                lines = [line.strip() for line in response.text.splitlines() if line.strip()]
                print(f"✅ 成功抓取 {url}: {len(lines)} 行")
                return lines
            else:
                print(f"❌ 抓取 {url} 失败，状态码: {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"⏰ 抓取 {url} 超时")
        except Exception as e:
            print(f"❌ 抓取 {url} 失败: {str(e)[:100]}...")
        return []
    
    if not URL_SOURCES:
        print("⚠️  没有配置在线源URL")
        return online_streams
    
    print("🌐 正在抓取在线源...")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(URL_SOURCES), 5)) as executor:
            future_to_url = {executor.submit(fetch_single_url, url): url for url in URL_SOURCES}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    online_streams.extend(result)
                except Exception as e:
                    print(f"❌ 处理 {url} 时出错: {e}")
        
        print(f"✅ 在线源抓取完成，共获取 {len(online_streams)} 行数据")
    except Exception as e:
        print(f"❌ 抓取在线源时发生错误: {e}")
    
    return online_streams

def parse_stream_line(line):
    """
    解析流数据行，提取频道名称和URL
    返回: (channel_name, url) 或 None
    """
    # 跳过M3U格式的EXTINF行
    if line.startswith('#EXTINF'):
        return None
    
    # 跳过注释行和空行
    if not line or line.startswith('#'):
        return None
    
    # 尝试匹配标准格式: 频道名称,URL
    match = channel_pattern.match(line)
    if match:
        channel_name = match.group(1).strip()
        url = match.group(2).strip()
        return (channel_name, url)
    
    # 尝试其他可能的格式
    if ',' in line:
        parts = line.split(',', 1)
        if len(parts) == 2 and parts[1].startswith(('http://', 'https://')):
            return (parts[0].strip(), parts[1].strip())
    
    return None

def parse_m3u_content(content):
    """
    解析M3U格式内容
    返回: [(channel_name, url)] 列表
    """
    channels = []
    lines = content.splitlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF'):
            # 提取频道名称
            channel_name = None
            
            # 尝试从tvg-name属性提取
            tvg_match = extinf_pattern.search(line)
            if tvg_match:
                channel_name = tvg_match.group(1)
            else:
                # 从EXTINF行末尾提取
                name_match = extinf_name_pattern.search(line)
                if name_match:
                    channel_name = name_match.group(1)
            
            # 下一行应该是URL
            if i + 1 < len(lines) and channel_name:
                url_line = lines[i + 1].strip()
                if url_line and not url_line.startswith('#'):
                    channels.append((channel_name, url_line))
                    i += 2
                    continue
        i += 1
    
    return channels

def build_channel_database(stream_lines):
    """
    构建频道数据库
    返回: {channel_name: [url1, url2, ...]}
    """
    print("📊 正在构建频道数据库...")
    channel_db = {}
    
    for line in stream_lines:
        result = parse_stream_line(line)
        if result:
            channel_name, url = result
            
            # 标准化频道名称（去除多余空格）
            channel_name = re.sub(r'\s+', ' ', channel_name).strip()
            
            if channel_name not in channel_db:
                channel_db[channel_name] = []
            
            # 避免重复URL
            if url not in channel_db[channel_name]:
                channel_db[channel_name].append(url)
    
    print(f"✅ 频道数据库构建完成，共 {len(channel_db)} 个频道")
    return channel_db

def test_stream_quality(url):
    """
    测试流质量
    返回: (is_alive, response_time) 或 (False, None) 如果测试失败
    """
    try:
        start_time = time.time()
        response = requests.head(url, timeout=REQUEST_TIMEOUT, verify=False, 
                               headers={'User-Agent': 'Mozilla/5.0'})
        end_time = time.time()
        
        response_time = round((end_time - start_time) * 1000)  # 转换为毫秒
        
        if response.status_code == 200:
            return (True, response_time)
        else:
            return (False, None)
    except:
        return (False, None)

def select_best_streams(urls, max_streams=MAX_STREAMS_PER_CHANNEL):
    """
    为频道选择最佳流
    返回: 排序后的URL列表
    """
    if not urls:
        return []
    
    # 如果URL数量较少，直接返回
    if len(urls) <= max_streams:
        return urls
    
    print(f"  🔍 测试频道流质量 ({len(urls)} 个流)...")
    valid_streams = []
    
    # 使用线程池测试流质量
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(test_stream_quality, url): url for url in urls}
        
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                is_alive, response_time = future.result()
                if is_alive:
                    valid_streams.append((url, response_time))
            except:
                pass
    
    # 按响应时间排序（快的在前）
    valid_streams.sort(key=lambda x: x[1] if x[1] is not None else float('inf'))
    
    # 返回最佳流，限制数量
    best_streams = [stream[0] for stream in valid_streams[:max_streams]]
    
    print(f"  ✅ 找到 {len(best_streams)} 个有效流")
    return best_streams

def generate_output_files(template_channels, channel_db):
    """
    生成输出文件
    """
    print("📝 正在生成输出文件...")
    
    txt_lines = []
    m3u_lines = ['#EXTM3U']
    
    current_group = "默认分组"
    
    for line in template_channels:
        # 处理分组行
        if '#genre#' in line:
            group_name = line.replace(',#genre#', '').strip()
            current_group = group_name
            txt_lines.append(line)
            continue
        
        # 处理频道行
        if ',' in line:
            parts = line.split(',', 1)
            if len(parts) == 2:
                template_channel = parts[0].strip()
                template_url = parts[1].strip()
                
                # 在数据库中查找匹配的频道
                matched_urls = []
                for db_channel, db_urls in channel_db.items():
                    # 简单的名称匹配（可以在这里改进匹配算法）
                    if template_channel.lower() in db_channel.lower() or db_channel.lower() in template_channel.lower():
                        matched_urls.extend(db_urls)
                
                # 选择最佳流
                best_urls = select_best_streams(matched_urls)
                
                if best_urls:
                    # 使用找到的最佳流
                    for url in best_urls:
                        txt_lines.append(f"{template_channel},{url}")
                        m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{template_channel}')
                        m3u_lines.append(url)
                else:
                    # 没有找到匹配的流，使用模板中的URL
                    txt_lines.append(line)
                    m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{template_channel}')
                    m3u_lines.append(template_url)
    
    # 写入TXT文件
    try:
        with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(txt_lines))
        print(f"✅ 生成TXT文件: {OUTPUT_TXT}，共 {len(txt_lines)} 行")
    except Exception as e:
        print(f"❌ 写入TXT文件失败: {e}")
    
    # 写入M3U文件
    try:
        with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
            f.write('\n'.join(m3u_lines))
        print(f"✅ 生成M3U文件: {OUTPUT_M3U}，共 {len(m3u_lines)} 行")
    except Exception as e:
        print(f"❌ 写入M3U文件失败: {e}")
    
    return len([line for line in txt_lines if ',' in line and '#genre#' not in line])

def main():
    """主函数"""
    print("🎬 IPTV频道整理工具开始运行...")
    start_time = time.time()
    
    # 1. 加载模板频道
    template_channels = load_template_channels()
    if not template_channels:
        print("❌ 无法加载模板频道，程序退出")
        return
    
    # 2. 加载本地源
    local_streams = load_local_sources()
    
    # 3. 抓取在线源
    online_streams = fetch_online_sources()
    
    # 4. 合并所有流数据
    all_streams = local_streams + online_streams
    if not all_streams:
        print("❌ 没有获取到任何流数据，程序退出")
        return
    
    print(f"📊 总共获取 {len(all_streams)} 个流数据")
    
    # 5. 构建频道数据库
    channel_db = build_channel_database(all_streams)
    
    # 6. 生成输出文件
    total_channels = generate_output_files(template_channels, channel_db)
    
    # 统计信息
    end_time = time.time()
    execution_time = round(end_time - start_time, 2)
    
    print("\n" + "="*50)
    print("📊 执行统计:")
    print(f"  模板频道: {len([c for c in template_channels if '#genre#' not in c and ',' in c])} 个")
    print(f"  源数据流: {len(all_streams)} 个")
    print(f"  发现频道: {len(channel_db)} 个")
    print(f"  输出频道: {total_channels} 个")
    print(f"  执行时间: {execution_time} 秒")
    print(f"  输出文件: {OUTPUT_TXT}, {OUTPUT_M3U}")
    print("="*50)

if __name__ == "__main__":
    # 禁用SSL警告
    requests.packages.urllib3.disable_warnings()
    
    main()
