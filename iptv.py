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
# 源URL列表
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
MAX_STREAMS_PER_CHANNEL = 5

# 请求超时时间（秒）
REQUEST_TIMEOUT = 8

# 测速超时时间（秒）
SPEED_TEST_TIMEOUT = 12

# 最大线程数
MAX_WORKERS = 20

# ============================ 正则表达式 ============================
# IPv4地址匹配
ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')

# 频道名称和URL匹配
channel_pattern = re.compile(r"^([^,]+?),\s*(https?://.+)", re.IGNORECASE)

# M3U格式解析
extinf_pattern = re.compile(r'tvg-name="([^"]*)"', re.IGNORECASE)
extinf_name_pattern = re.compile(r'#EXTINF:.*?,(.+)', re.IGNORECASE)

def create_correct_template():
    """创建正确的模板文件格式（只有频道名称）"""
    print("📝 创建正确的模板文件格式...")
    
    template_content = """央视频道,#genre#
CCTV-1
CCTV-2
CCTV-3
CCTV-4
CCTV-5
CCTV-5+
CCTV-6
CCTV-7
CCTV-8
CCTV-9
CCTV-10
CCTV-11
CCTV-12
CCTV-13
CCTV-14
CCTV-15
CCTV-16
CCTV-17

卫视频道,#genre#
安徽卫视
广东卫视
浙江卫视
湖南卫视
北京卫视
湖北卫视
黑龙江卫视
重庆卫视
东方卫视
东南卫视
甘肃卫视
凤凰卫视
广西卫视
贵州卫视
海南卫视
河北卫视
河南卫视
江苏卫视
江西卫视
吉林卫视
辽宁卫视
内蒙古卫视
宁夏卫视
青海卫视
山东卫视
山西卫视
陕西卫视
四川卫视
天津卫视
西藏卫视
新疆卫视
云南卫视

其他频道,#genre#
安徽国际
安徽影视
第一财经
梨园频道"""
    
    try:
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            f.write(template_content)
        print(f"✅ 创建模板文件: {TEMPLATE_FILE}")
        return True
    except Exception as e:
        print(f"❌ 创建模板文件失败: {e}")
        return False

def clean_channel_name(channel_name):
    """
    清理频道名称，去除不需要的后缀
    """
    # 去除常见的后缀
    suffixes = ['综合', '高清', '超清', '标清', 'HD', 'FHD', '4K', '直播', '频道', '卫视台']
    pattern = r'[\(（].*?[\)）]|\s*-\s*.*$|\s*–\s*.*$'
    
    cleaned_name = channel_name.strip()
    
    # 去除括号内容
    cleaned_name = re.sub(pattern, '', cleaned_name)
    
    # 去除后缀
    for suffix in suffixes:
        cleaned_name = cleaned_name.replace(suffix, '').strip()
    
    # 去除多余空格
    cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
    
    return cleaned_name

def format_channel_name_for_output(template_channel):
    """
    格式化输出用的频道名称，确保显示完整的标准名称
    """
    # 保持模板中的原始名称，不做清理
    return template_channel.strip()

def load_template_channels():
    """加载模板频道列表（只有频道名称）"""
    if not os.path.exists(TEMPLATE_FILE):
        print(f"❌ 模板文件 {TEMPLATE_FILE} 不存在")
        if not create_correct_template():
            return []
    
    template_channels = []
    template_channel_names = []  # 只存储频道名称
    
    try:
        print(f"📁 正在加载模板文件: {TEMPLATE_FILE}")
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    template_channels.append(line)
                    
                    # 只提取频道名称（非分组行）
                    if '#genre#' not in line and ',' not in line:
                        template_channel_names.append(line)
        
        # 统计信息
        genre_lines = [line for line in template_channels if '#genre#' in line]
        
        print(f"✅ 模板文件加载完成:")
        print(f"  - 总行数: {len(template_channels)}")
        print(f"  - 分组数: {len(genre_lines)}")
        print(f"  - 频道数: {len(template_channel_names)}")
        
        if not template_channel_names:
            print("❌ 模板中没有有效的频道名称")
            return []
        
        # 显示前几个频道名称作为示例
        print("频道名称示例:")
        for i, channel in enumerate(template_channel_names[:8], 1):
            print(f"  {i}. {channel}")
        
        return template_channels
        
    except Exception as e:
        print(f"❌ 加载模板文件失败: {e}")
        return []

def load_local_sources():
    """优先加载本地源文件"""
    local_streams = []
    if not os.path.exists(LOCAL_SOURCE_FILE):
        print(f"⚠️  本地源文件 {LOCAL_SOURCE_FILE} 不存在，跳过")
        return local_streams
    
    try:
        print(f"📁 正在优先加载本地源文件: {LOCAL_SOURCE_FILE}")
        with open(LOCAL_SOURCE_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    local_streams.append(('local', line))
        print(f"✅ 本地源文件加载完成，共 {len(local_streams)} 个流")
    except Exception as e:
        print(f"❌ 加载本地源文件失败: {e}")
    
    return local_streams

def fetch_online_sources():
    """抓取在线源数据"""
    online_streams = []
    
    def fetch_single_url(url):
        """获取单个URL的源数据"""
        try:
            print(f"🌐 正在抓取: {url}")
            response = requests.get(url, timeout=25, verify=False)
            response.encoding = 'utf-8'
            if response.status_code == 200:
                lines = [line.strip() for line in response.text.splitlines() if line.strip()]
                print(f"✅ 成功抓取 {url}: {len(lines)} 行")
                return (url, lines)
            else:
                print(f"❌ 抓取 {url} 失败，状态码: {response.status_code}")
                return (url, [])
        except requests.exceptions.Timeout:
            print(f"⏰ 抓取 {url} 超时")
            return (url, [])
        except Exception as e:
            print(f"❌ 抓取 {url} 失败: {str(e)[:100]}...")
            return (url, [])
    
    if not URL_SOURCES:
        print("⚠️  没有配置在线源URL")
        return online_streams
    
    print("🌐 正在抓取在线源...")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(URL_SOURCES), 6)) as executor:
            future_to_url = {executor.submit(fetch_single_url, url): url for url in URL_SOURCES}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    source_url, result = future.result()
                    online_streams.extend([(source_url, line) for line in result])
                except Exception as e:
                    print(f"❌ 处理 {url} 时出错: {e}")
        
        print(f"✅ 在线源抓取完成，共获取 {len(online_streams)} 行数据")
    except Exception as e:
        print(f"❌ 抓取在线源时发生错误: {e}")
    
    return online_streams

def parse_stream_line(source, line):
    """解析流数据行，提取频道名称和URL"""
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
        return (channel_name, url, source)
    
    # 尝试其他可能的格式
    if ',' in line:
        parts = line.split(',', 1)
        if len(parts) == 2 and parts[1].startswith(('http://', 'https://')):
            return (parts[0].strip(), parts[1].strip(), source)
    
    return None

def build_complete_channel_database(local_streams, online_streams):
    """构建完整的频道数据库"""
    print("📊 正在构建完整频道数据库...")
    channel_db = {}
    processed_count = 0
    
    all_streams = local_streams + online_streams
    
    for source, line in all_streams:
        result = parse_stream_line(source, line)
        if result:
            channel_name, url, source_info = result
            # 清理频道名称用于匹配
            cleaned_name = clean_channel_name(channel_name)
            
            if cleaned_name not in channel_db:
                channel_db[cleaned_name] = []
            
            if not any(existing_url == url for existing_url, _, _ in channel_db[cleaned_name]):
                channel_db[cleaned_name].append((url, source_info, {}))
            processed_count += 1
    
    print(f"✅ 完整频道数据库构建完成:")
    print(f"  - 处理数据行: {processed_count}")
    print(f"  - 唯一频道数: {len(channel_db)}")
    print(f"  - 总流数量: {sum(len(urls) for urls in channel_db.values())}")
    
    # 显示频道统计
    print("\n📈 频道数量统计:")
    channel_counts = {}
    for channel_name, urls in channel_db.items():
        count = len(urls)
        if count not in channel_counts:
            channel_counts[count] = []
        channel_counts[count].append(channel_name)
    
    for count in sorted(channel_counts.keys(), reverse=True)[:10]:
        channels = channel_counts[count]
        print(f"  - {count}个流: {len(channels)}个频道")
        if count >= 3:
            print(f"    示例: {', '.join(channels[:2])}")
    
    return channel_db

def comprehensive_speed_test(url):
    """全面测速功能"""
    try:
        start_time = time.time()
        response = requests.head(url, timeout=REQUEST_TIMEOUT, verify=False, 
                               headers={'User-Agent': 'Mozilla/5.0'})
        head_time = time.time()
        response_time_ms = round((head_time - start_time) * 1000)
        
        if response.status_code != 200:
            return (False, None, None, f"HTTP {response.status_code}")
        
        download_speed = None
        try:
            chunk_size = 1024 * 50
            start_download = time.time()
            download_response = requests.get(url, timeout=SPEED_TEST_TIMEOUT, 
                                           verify=False, stream=True,
                                           headers={'User-Agent': 'Mozilla/5.0'})
            
            downloaded = 0
            for chunk in download_response.iter_content(chunk_size=chunk_size):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded >= chunk_size:
                        break
            
            end_download = time.time()
            download_time = end_download - start_download
            
            if download_time > 0.1:
                download_speed = round((downloaded / 1024) / download_time)
            
            download_response.close()
            
        except Exception as e:
            download_speed = None
        
        return (True, response_time_ms, download_speed, None)
        
    except requests.exceptions.Timeout:
        return (False, None, None, "Timeout")
    except requests.exceptions.ConnectionError:
        return (False, None, None, "Connection Error")
    except Exception as e:
        return (False, None, None, str(e)[:50])

def speed_test_all_channels(channel_db):
    """对所有频道进行测速"""
    print("\n🚀 开始全面测速...")
    
    total_urls = sum(len(urls) for urls in channel_db.values())
    print(f"📊 需要测速的URL总数: {total_urls}")
    
    all_urls_to_test = []
    url_to_channel_map = {}
    
    for channel_name, urls in channel_db.items():
        for url, source, _ in urls:
            all_urls_to_test.append(url)
            url_to_channel_map[url] = channel_name
    
    speed_stats = {
        'total_tested': 0,
        'success_count': 0,
        'timeout_count': 0,
        'error_count': 0,
        'response_times': []
    }
    
    print("⏱️  正在进行全面测速...")
    with tqdm(total=len(all_urls_to_test), desc="全面测速", unit="URL", 
              bar_format='{l_bar}{bar:30}{r_bar}{bar:-30b}') as pbar:
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(comprehensive_speed_test, url): url for url in all_urls_to_test}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                channel_name = url_to_channel_map[url]
                
                try:
                    is_alive, response_time, download_speed, error_msg = future.result()
                    speed_stats['total_tested'] += 1
                    
                    for i, (stream_url, source, speed_info) in enumerate(channel_db[channel_name]):
                        if stream_url == url:
                            channel_db[channel_name][i] = (
                                stream_url, 
                                source, 
                                {
                                    'alive': is_alive,
                                    'response_time': response_time,
                                    'download_speed': download_speed,
                                    'error': error_msg,
                                    'score': calculate_stream_score(is_alive, response_time, download_speed)
                                }
                            )
                            break
                    
                    if is_alive:
                        speed_stats['success_count'] += 1
                        if response_time:
                            speed_stats['response_times'].append(response_time)
                    else:
                        if error_msg == "Timeout":
                            speed_stats['timeout_count'] += 1
                        else:
                            speed_stats['error_count'] += 1
                    
                    pbar.set_postfix(
                        success=f"{speed_stats['success_count']}/{speed_stats['total_tested']}",
                        avg_time=f"{sum(speed_stats['response_times'])/len(speed_stats['response_times']) if speed_stats['response_times'] else 0:.0f}ms"
                    )
                    pbar.update(1)
                    
                except Exception as e:
                    pbar.update(1)
    
    if speed_stats['response_times']:
        avg_response_time = sum(speed_stats['response_times']) / len(speed_stats['response_times'])
        min_response_time = min(speed_stats['response_times'])
        max_response_time = max(speed_stats['response_times'])
    else:
        avg_response_time = min_response_time = max_response_time = 0
    
    print(f"\n✅ 全面测速完成:")
    print(f"  - 测试总数: {speed_stats['total_tested']}")
    print(f"  - 成功: {speed_stats['success_count']} ({speed_stats['success_count']/speed_stats['total_tested']*100:.1f}%)")
    print(f"  - 超时: {speed_stats['timeout_count']}")
    print(f"  - 错误: {speed_stats['error_count']}")
    print(f"  - 平均响应: {avg_response_time:.0f}ms")
    print(f"  - 最快响应: {min_response_time}ms")
    print(f"  - 最慢响应: {max_response_time}ms")
    
    return channel_db, speed_stats

def calculate_stream_score(is_alive, response_time, download_speed):
    """计算流质量综合评分"""
    if not is_alive:
        return 0
    
    score = 0
    
    if response_time:
        if response_time <= 100:
            score += 60
        elif response_time <= 300:
            score += 50
        elif response_time <= 500:
            score += 40
        elif response_time <= 1000:
            score += 30
        elif response_time <= 2000:
            score += 20
        else:
            score += 10
    
    if download_speed:
        if download_speed >= 1000:
            score += 40
        elif download_speed >= 500:
            score += 30
        elif download_speed >= 200:
            score += 20
        elif download_speed >= 100:
            score += 10
        else:
            score += 5
    
    return score

def is_channel_match(template_channel, db_channel):
    """
    精准匹配频道名称，特别是CCTV频道
    """
    template_lower = template_channel.lower().strip()
    db_lower = db_channel.lower().strip()
    
    # 完全匹配
    if template_lower == db_lower:
        return True
    
    # 对于CCTV频道进行精准匹配
    if 'cctv' in template_lower and 'cctv' in db_lower:
        # 提取CCTV数字部分
        template_nums = re.findall(r'cctv[-\s]*(\d+\+?)', template_lower)
        db_nums = re.findall(r'cctv[-\s]*(\d+\+?)', db_lower)
        
        if template_nums and db_nums:
            # 数字部分完全匹配
            if template_nums[0] == db_nums[0]:
                return True
        
        # 处理CCTV-5+等特殊情况
        if 'cctv-5+' in template_lower and any(x in db_lower for x in ['cctv5+', 'cctv-5+', 'cctv5plus']):
            return True
        if 'cctv5+' in template_lower and any(x in db_lower for x in ['cctv5+', 'cctv-5+', 'cctv5plus']):
            return True
    
    # 对于卫视频道进行精准匹配
    if '卫视' in template_channel and '卫视' in db_channel:
        template_province = template_channel.replace('卫视', '').strip()
        db_province = db_channel.replace('卫视', '').strip()
        if template_province == db_province:
            return True
        # 处理简称匹配
        if template_province in db_province or db_province in template_province:
            return True
    
    # 其他频道的宽松匹配
    template_no_space = template_lower.replace(' ', '').replace('-', '')
    db_no_space = db_lower.replace(' ', '').replace('-', '')
    
    if template_no_space in db_no_space or db_no_space in template_no_space:
        return True
    
    return False

def find_matching_channels(template_channel, channel_db):
    """查找匹配的频道"""
    matched_urls = []
    
    for db_channel, urls in channel_db.items():
        if is_channel_match(template_channel, db_channel):
            valid_urls = [(url, source, info) for url, source, info in urls 
                        if info.get('alive', False)]
            matched_urls.extend(valid_urls)
    
    return matched_urls

def match_template_channels(template_channels, channel_db):
    """匹配模板频道并选择最佳流"""
    print("\n🎯 开始模板频道匹配...")
    
    txt_lines = []
    m3u_lines = ['#EXTM3U']
    current_group = "默认分组"
    matched_count = 0
    
    for line in template_channels:
        if '#genre#' in line:
            group_name = line.replace(',#genre#', '').strip()
            current_group = group_name
            txt_lines.append(line)
            continue
        
        # 模板行只有频道名称（没有URL）
        if line and not line.endswith('#genre#'):
            # 使用原始模板名称，不进行清理
            template_channel_original = line
            # 用于匹配的清理后名称
            template_channel_for_match = clean_channel_name(line)
            
            print(f"  🔍 查找频道: {template_channel_original}")
            
            matched_urls = find_matching_channels(template_channel_for_match, channel_db)
            
            if matched_urls:
                matched_urls.sort(key=lambda x: x[2].get('score', 0), reverse=True)
                best_urls = matched_urls[:MAX_STREAMS_PER_CHANNEL]
                
                for url, source, info in best_urls:
                    # 使用原始模板名称输出，确保显示完整的"CCTV-1"等名称
                    output_channel_name = format_channel_name_for_output(template_channel_original)
                    txt_lines.append(f"{output_channel_name},{url}")
                    m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{output_channel_name}')
                    m3u_lines.append(url)
                
                matched_count += 1
                print(f"  ✅ {template_channel_original}: 找到 {len(best_urls)} 个优质流")
            else:
                print(f"  ❌ {template_channel_original}: 未找到有效流")
    
    try:
        with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(txt_lines))
        print(f"✅ 生成TXT文件: {OUTPUT_TXT}，共 {len(txt_lines)} 行")
    except Exception as e:
        print(f"❌ 写入TXT文件失败: {e}")
    
    try:
        with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
            f.write('\n'.join(m3u_lines))
        print(f"✅ 生成M3U文件: {OUTPUT_M3U}，共 {len(m3u_lines)} 行")
    except Exception as e:
        print(f"❌ 写入M3U文件失败: {e}")
    
    print(f"🎯 模板匹配完成: {matched_count} 个频道匹配成功")
    return matched_count

def main():
    """主函数"""
    print("🎬 IPTV频道整理工具开始运行...")
    start_time = time.time()
    
    # 1. 优先加载本地源
    print("\n" + "="*50)
    print("步骤1: 优先加载本地源")
    local_streams = load_local_sources()
    
    # 2. 抓取在线源
    print("\n" + "="*50)
    print("步骤2: 抓取在线源")
    online_streams = fetch_online_sources()
    
    # 3. 合并所有源构建完整数据库
    print("\n" + "="*50)
    print("步骤3: 合并所有源构建完整数据库")
    channel_db = build_complete_channel_database(local_streams, online_streams)
    
    # 4. 对所有频道进行测速
    print("\n" + "="*50)
    print("步骤4: 全面测速和延时测试")
    channel_db, speed_stats = speed_test_all_channels(channel_db)
    
    # 5. 加载模板并进行匹配
    print("\n" + "="*50)
    print("步骤5: 模板频道匹配")
    template_channels = load_template_channels()
    if template_channels:
        matched_count = match_template_channels(template_channels, channel_db)
    else:
        matched_count = 0
        print("❌ 无法加载模板，跳过匹配")
    
    # 最终统计
    end_time = time.time()
    execution_time = round(end_time - start_time, 2)
    
    print("\n" + "="*60)
    print("🎉 执行完成!")
    print("="*60)
    print("📊 最终统计:")
    print(f"  ⏱️  总执行时间: {execution_time} 秒")
    print(f"  📺 总频道数: {len(channel_db)}")
    print(f"  🔗 总流数量: {sum(len(urls) for urls in channel_db.values())}")
    print(f"  ✅ 有效流数量: {speed_stats['success_count']}")
    print(f"  🎯 模板匹配: {matched_count} 个频道")
    print(f"  📈 平均响应: {sum(speed_stats['response_times'])/len(speed_stats['response_times']) if speed_stats['response_times'] else 0:.0f}ms")
    print(f"\n📁 输出文件:")
    print(f"  - {OUTPUT_TXT} (频道列表)")
    print(f"  - {OUTPUT_M3U} (M3U播放列表)")
    print("="*60)

if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()
    main()
