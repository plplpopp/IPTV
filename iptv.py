import requests
import pandas as pd
import re
import os
import time
import concurrent.futures
from urllib.parse import urlparse
from tqdm import tqdm
import sys
import json

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
OUTPUT_SPEED_TEST = "speed_test_results.txt"
OUTPUT_CHANNEL_STATS = "channel_stats.json"

# 每个频道保留的接口数量
MAX_STREAMS_PER_CHANNEL = 5

# 请求超时时间（秒）
REQUEST_TIMEOUT = 8

# 测速超时时间（秒）
SPEED_TEST_TIMEOUT = 12

# 最大线程数
MAX_WORKERS = 20

# 测速模式
SPEED_TEST_MODE = "all"  # "all": 测试所有源, "sample": 抽样测试

# ============================ 正则表达式 ============================
# IPv4地址匹配
ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')

# 频道名称和URL匹配
channel_pattern = re.compile(r"^([^,]+?),\s*(https?://.+)", re.IGNORECASE)

# M3U格式解析
extinf_pattern = re.compile(r'tvg-name="([^"]*)"', re.IGNORECASE)
extinf_name_pattern = re.compile(r'#EXTINF:.*?,(.+)', re.IGNORECASE)

def create_default_template():
    """创建默认模板文件"""
    print("📝 创建默认模板文件...")
    
    template_content = """央视频道,#genre#
CCTV-1 综合,http://example.com/cctv1
CCTV-2 财经,http://example.com/cctv2
CCTV-3 综艺,http://example.com/cctv3
CCTV-4 中文国际,http://example.com/cctv4
CCTV-5 体育,http://example.com/cctv5
CCTV-5+ 体育赛事,http://example.com/cctv5plus
CCTV-6 电影,http://example.com/cctv6
CCTV-7 国防军事,http://example.com/cctv7
CCTV-8 电视剧,http://example.com/cctv8
CCTV-9 纪录,http://example.com/cctv9
CCTV-10 科教,http://example.com/cctv10
CCTV-11 戏曲,http://example.com/cctv11
CCTV-12 社会与法,http://example.com/cctv12
CCTV-13 新闻,http://example.com/cctv13
CCTV-14 少儿,http://example.com/cctv14
CCTV-15 音乐,http://example.com/cctv15
CCTV-16 奥林匹克,http://example.com/cctv16
CCTV-17 农业农村,http://example.com/cctv17

卫视频道,#genre#
湖南卫视,http://example.com/hunan
浙江卫视,http://example.com/zhejiang
江苏卫视,http://example.com/jiangsu
东方卫视,http://example.com/dongfang
北京卫视,http://example.com/beijing
天津卫视,http://example.com/tianjin
山东卫视,http://example.com/shandong
安徽卫视,http://example.com/anhui
广东卫视,http://example.com/guangdong
深圳卫视,http://example.com/shenzhen
辽宁卫视,http://example.com/liaoning
黑龙江卫视,http://example.com/heilongjiang
湖北卫视,http://example.com/hubei
河南卫视,http://example.com/henan
四川卫视,http://example.com/sichuan
重庆卫视,http://example.com/chongqing
东南卫视,http://example.com/dongnan
江西卫视,http://example.com/jiangxi

其他频道,#genre#
北京纪实,http://example.com/beijingjishi
上海纪实,http://example.com/shanghaijishi
金鹰卡通,http://example.com/jinyingkatong
卡酷少儿,http://example.com/kakushaonian
炫动卡通,http://example.com/xuandongkatong"""
    
    try:
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            f.write(template_content)
        print(f"✅ 创建默认模板文件: {TEMPLATE_FILE}")
        return True
    except Exception as e:
        print(f"❌ 创建模板文件失败: {e}")
        return False

def load_template_channels():
    """加载模板频道列表"""
    if not os.path.exists(TEMPLATE_FILE):
        print(f"❌ 模板文件 {TEMPLATE_FILE} 不存在")
        if not create_default_template():
            return []
    
    template_channels = []
    try:
        print(f"📁 正在加载模板文件: {TEMPLATE_FILE}")
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    template_channels.append(line)
        
        # 统计信息
        genre_lines = [line for line in template_channels if '#genre#' in line]
        channel_lines = [line for line in template_channels if '#genre#' not in line and ',' in line]
        
        print(f"✅ 模板文件加载完成:")
        print(f"  - 总行数: {len(template_channels)}")
        print(f"  - 分组数: {len(genre_lines)}")
        print(f"  - 频道数: {len(channel_lines)}")
        
        if not channel_lines:
            print("⚠️  警告: 模板文件中没有找到有效的频道行")
        
    except Exception as e:
        print(f"❌ 加载模板文件失败: {e}")
        return []
    
    return template_channels

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
                    local_streams.append(('local', line))  # 标记来源为本地
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
                    # 标记来源为在线
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
    """
    构建完整的频道数据库（合并所有源）
    返回: {channel_name: [(url, source, speed_info)]}
    """
    print("📊 正在构建完整频道数据库...")
    channel_db = {}
    processed_count = 0
    
    # 处理所有流数据（本地优先）
    all_streams = local_streams + online_streams
    
    for source, line in all_streams:
        result = parse_stream_line(source, line)
        if result:
            channel_name, url, source_info = result
            
            # 标准化频道名称
            channel_name = re.sub(r'\s+', ' ', channel_name).strip()
            
            if channel_name not in channel_db:
                channel_db[channel_name] = []
            
            # 避免重复URL
            if not any(existing_url == url for existing_url, _, _ in channel_db[channel_name]):
                channel_db[channel_name].append((url, source_info, {}))  # 预留测速信息位置
            
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
    
    # 按流数量排序显示
    for count in sorted(channel_counts.keys(), reverse=True)[:10]:
        channels = channel_counts[count]
        print(f"  - {count}个流: {len(channels)}个频道")
        if count >= 5:  # 显示流数量多的频道示例
            print(f"    示例: {', '.join(channels[:3])}")
    
    return channel_db

def comprehensive_speed_test(url):
    """
    全面测速功能 - 测试响应时间和连接质量
    返回: (is_alive, response_time_ms, download_speed_kbps, error_message)
    """
    try:
        # 第一阶段：测试响应时间
        start_time = time.time()
        response = requests.head(url, timeout=REQUEST_TIMEOUT, verify=False, 
                               headers={'User-Agent': 'Mozilla/5.0'})
        head_time = time.time()
        response_time_ms = round((head_time - start_time) * 1000)
        
        if response.status_code != 200:
            return (False, None, None, f"HTTP {response.status_code}")
        
        # 第二阶段：简单下载测试
        download_speed = None
        try:
            chunk_size = 1024 * 50  # 50KB
            start_download = time.time()
            download_response = requests.get(url, timeout=SPEED_TEST_TIMEOUT, 
                                           verify=False, stream=True,
                                           headers={'User-Agent': 'Mozilla/5.0'})
            
            downloaded = 0
            for chunk in download_response.iter_content(chunk_size=chunk_size):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded >= chunk_size:  # 下载50KB后停止
                        break
            
            end_download = time.time()
            download_time = end_download - start_download
            
            if download_time > 0.1:  # 至少0.1秒才计算速度
                download_speed = round((downloaded / 1024) / download_time)  # KB/s
            
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
    """
    对所有频道进行测速
    返回: 更新后的频道数据库和测速统计
    """
    print("\n🚀 开始全面测速...")
    
    total_urls = sum(len(urls) for urls in channel_db.values())
    print(f"📊 需要测速的URL总数: {total_urls}")
    
    # 准备所有需要测速的URL
    all_urls_to_test = []
    url_to_channel_map = {}
    
    for channel_name, urls in channel_db.items():
        for url, source, _ in urls:
            all_urls_to_test.append(url)
            url_to_channel_map[url] = channel_name
    
    # 测速统计
    speed_stats = {
        'total_tested': 0,
        'success_count': 0,
        'timeout_count': 0,
        'error_count': 0,
        'response_times': []
    }
    
    # 使用进度条进行测速
    print("⏱️  正在进行全面测速...")
    with tqdm(total=len(all_urls_to_test), desc="全面测速", unit="URL", 
              bar_format='{l_bar}{bar:30}{r_bar}{bar:-30b}') as pbar:
        
        # 使用线程池进行并发测速
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_url = {executor.submit(comprehensive_speed_test, url): url for url in all_urls_to_test}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                channel_name = url_to_channel_map[url]
                
                try:
                    is_alive, response_time, download_speed, error_msg = future.result()
                    speed_stats['total_tested'] += 1
                    
                    # 更新频道数据库中的测速信息
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
                    
                    # 更新进度条
                    pbar.set_postfix(
                        success=f"{speed_stats['success_count']}/{speed_stats['total_tested']}",
                        avg_time=f"{sum(speed_stats['response_times'])/len(speed_stats['response_times']) if speed_stats['response_times'] else 0:.0f}ms"
                    )
                    pbar.update(1)
                    
                except Exception as e:
                    pbar.update(1)
    
    # 计算测速统计
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
    
    # 响应时间评分 (0-60分)
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
    
    # 下载速度评分 (0-40分)
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

def generate_channel_stats(channel_db):
    """生成频道统计信息"""
    print("\n📈 生成频道统计信息...")
    
    stats = {
        'total_channels': len(channel_db),
        'total_streams': sum(len(urls) for urls in channel_db.values()),
        'channels_by_stream_count': {},
        'channels_with_speed_info': {},
        'top_channels': []
    }
    
    # 统计每个频道的流数量
    for channel_name, urls in channel_db.items():
        stream_count = len(urls)
        alive_count = sum(1 for _, _, info in urls if info.get('alive', False))
        
        if stream_count not in stats['channels_by_stream_count']:
            stats['channels_by_stream_count'][stream_count] = 0
        stats['channels_by_stream_count'][stream_count] += 1
        
        stats['channels_with_speed_info'][channel_name] = {
            'total_streams': stream_count,
            'alive_streams': alive_count,
            'alive_ratio': alive_count / stream_count if stream_count > 0 else 0,
            'best_response_time': min((info.get('response_time', 9999) for _, _, info in urls if info.get('alive', False)), default=0),
            'urls': [{'url': url, 'source': source, 'speed_info': info} for url, source, info in urls]
        }
    
    # 生成TOP频道列表（按流数量排序）
    sorted_channels = sorted(stats['channels_with_speed_info'].items(), 
                           key=lambda x: x[1]['total_streams'], reverse=True)
    
    stats['top_channels'] = sorted_channels[:20]  # 前20个频道
    
    # 保存统计信息到JSON文件
    try:
        with open(OUTPUT_CHANNEL_STATS, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"✅ 频道统计信息已保存到: {OUTPUT_CHANNEL_STATS}")
    except Exception as e:
        print(f"❌ 保存频道统计信息失败: {e}")
    
    # 显示统计摘要
    print(f"\n📊 频道统计摘要:")
    print(f"  - 总频道数: {stats['total_channels']}")
    print(f"  - 总流数量: {stats['total_streams']}")
    print(f"  - 平均每个频道流数: {stats['total_streams']/stats['total_channels']:.1f}")
    
    # 显示流数量分布
    print(f"\n📋 流数量分布:")
    for count in sorted(stats['channels_by_stream_count'].keys(), reverse=True)[:10]:
        if count >= 2:  # 只显示有2个以上流的频道
            print(f"  - {count}个流: {stats['channels_by_stream_count'][count]}个频道")
    
    # 显示TOP频道
    print(f"\n🏆 TOP频道 (按流数量):")
    for i, (channel, info) in enumerate(stats['top_channels'][:10], 1):
        print(f"  {i:2d}. {channel}: {info['total_streams']}个流 ({info['alive_streams']}个有效)")
    
    return stats

def match_template_channels(template_channels, channel_db):
    """匹配模板频道并选择最佳流"""
    print("\n🎯 开始模板频道匹配...")
    
    txt_lines = []
    m3u_lines = ['#EXTM3U']
    current_group = "默认分组"
    matched_count = 0
    
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
                
                # 查找匹配的频道
                matched_urls = []
                for db_channel, urls in channel_db.items():
                    if is_channel_match(template_channel, db_channel):
                        # 只选择有效的流
                        valid_urls = [(url, source, info) for url, source, info in urls 
                                    if info.get('alive', False)]
                        matched_urls.extend(valid_urls)
                
                if matched_urls:
                    # 按评分排序并选择最佳流
                    matched_urls.sort(key=lambda x: x[2].get('score', 0), reverse=True)
                    best_urls = matched_urls[:MAX_STREAMS_PER_CHANNEL]
                    
                    # 添加到输出
                    for url, source, info in best_urls:
                        speed_info = format_speed_info(info)
                        txt_lines.append(f"{template_channel}{speed_info},{url}")
                        m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{template_channel}{speed_info}')
                        m3u_lines.append(url)
                    
                    matched_count += 1
                    print(f"  ✅ {template_channel}: 找到 {len(best_urls)} 个优质流")
                else:
                    # 没有找到匹配的有效流，使用模板URL
                    txt_lines.append(line)
                    m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{template_channel}')
                    m3u_lines.append(template_url)
                    print(f"  ❌ {template_channel}: 未找到有效流")
    
    # 写入输出文件
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

def is_channel_match(template_channel, db_channel):
    """判断频道是否匹配"""
    template_lower = template_channel.lower()
    db_lower = db_channel.lower()
    
    # 多种匹配策略
    match_strategies = [
        template_lower in db_lower,
        db_lower in template_lower,
        template_lower.replace(' ', '') in db_lower.replace(' ', ''),
        template_lower.replace('cctv-', 'cctv') in db_lower.replace('cctv-', 'cctv'),
        any(word in db_lower for word in template_lower.split() if len(word) > 2)
    ]
    
    return any(match_strategies)

def format_speed_info(speed_info):
    """格式化测速信息"""
    if not speed_info.get('alive', False):
        return " | 无效"
    
    parts = []
    if speed_info.get('response_time'):
        parts.append(f"{speed_info['response_time']}ms")
    if speed_info.get('download_speed'):
        parts.append(f"{speed_info['download_speed']}KB/s")
    
    if parts:
        return " | " + " ".join(parts)
    else:
        return " | 有效"

def main():
    """主函数 - 按照新流程执行"""
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
    
    # 5. 生成频道统计信息
    print("\n" + "="*50)
    print("步骤5: 生成频道统计信息")
    channel_stats = generate_channel_stats(channel_db)
    
    # 6. 加载模板并进行匹配
    print("\n" + "="*50)
    print("步骤6: 模板频道匹配")
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
    print(f"  📺 总频道数: {channel_stats['total_channels']}")
    print(f"  🔗 总流数量: {channel_stats['total_streams']}")
    print(f"  ✅ 有效流数量: {speed_stats['success_count']}")
    print(f"  🎯 模板匹配: {matched_count} 个频道")
    print(f"  📈 平均响应: {sum(speed_stats['response_times'])/len(speed_stats['response_times']) if speed_stats['response_times'] else 0:.0f}ms")
    print(f"\n📁 输出文件:")
    print(f"  - {OUTPUT_TXT} (频道列表)")
    print(f"  - {OUTPUT_M3U} (M3U播放列表)")
    print(f"  - {OUTPUT_CHANNEL_STATS} (频道统计)")
    print(f"  - {OUTPUT_SPEED_TEST} (测速结果)")
    print("="*60)

if __name__ == "__main__":
    # 禁用SSL警告
    requests.packages.urllib3.disable_warnings()
    
    main()
