import requests
import pandas as pd
import re
import os
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import sys

###############################################################################
#                           配置区域 - 所有配置集中在此处                     #
###############################################################################

# =============================================================================
# 文件路径配置
# =============================================================================

# 本地源文件路径：包含自定义的直播源，格式为"频道名称,URL"或直接URL
LOCAL_SOURCE_FILE = "local.txt"

# 频道模板文件路径：定义输出文件中频道的排序顺序，每行一个频道名称
DEMO_TEMPLATE_FILE = "demo.txt"

# 输出文件路径：生成的直播源文件
OUTPUT_TXT_FILE = "iptv.txt"    # TXT格式输出文件
OUTPUT_M3U_FILE = "iptv.m3u"    # M3U格式输出文件

# =============================================================================
# 网络请求配置
# =============================================================================

# 在线直播源URL列表：程序会从这些URL获取直播源数据
ONLINE_SOURCE_URLS = [
     "https://ghfast.top/raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
     "https://gh-proxy.com/https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
     "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",  
     "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
     "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
     "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
     "https://gh-proxy.com/https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
     "http://47.120.41.246:8899/zb.txt",
]

# 请求超时时间（秒）：网络请求的最大等待时间
REQUEST_TIMEOUT = 10

# 用户代理头：模拟浏览器访问，避免被网站屏蔽
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# =============================================================================
# 并发处理配置
# =============================================================================

# 最大工作线程数：同时进行的网络请求数量
MAX_WORKERS = 10

# 频道测试并发数：同时测试的频道数量
CHANNEL_TEST_WORKERS = 5

# URL测试并发数：单个频道内同时测试的URL数量
URL_TEST_WORKERS = 8

# =============================================================================
# 频道处理配置
# =============================================================================

# 单个频道最大保留URL数量：每个频道最终保留的最佳源数量
MAX_URLS_PER_CHANNEL = 8

# 流测试超时时间（秒）：测试单个流媒体的最大时间
STREAM_TEST_TIMEOUT = 8

# =============================================================================
# 正则表达式配置
# =============================================================================

# IPv4地址匹配模式：识别IPv4格式的URL
IPV4_PATTERN = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')

# M3U格式解析模式：从EXTINF行中提取频道名称
EXTINF_PATTERN = re.compile(r'tvg-name="([^"]+)"')

# TXT格式解析模式：匹配"频道名称,URL"格式
TXT_LINE_PATTERN = re.compile(r"^(.+?),(?:\s*)(http.+)")

# 频道名称清理模式：移除文件名中的非法字符
CHANNEL_NAME_CLEAN_PATTERN = re.compile(r'[<>:"/\\|?*]')

###############################################################################
#                           程序代码区域 - 不要修改下面的代码                 #
###############################################################################

class StreamTester:
    """流媒体测试器 - 只测试响应延时"""
    
    def __init__(self):
        self.results_cache = {}
        self.lock = threading.Lock()
        self.test_count = 0
        self.success_count = 0
    
    def test_stream(self, program_name, stream_url):
        """测试单个流媒体的响应时间"""
        cache_key = f"{program_name}|{stream_url}"
        
        # 检查缓存
        if cache_key in self.results_cache:
            return self.results_cache[cache_key]
        
        self.test_count += 1
        start_time = time.time()
        
        try:
            # 使用HEAD请求测试响应时间
            response = requests.head(
                stream_url, 
                timeout=STREAM_TEST_TIMEOUT,
                headers=HEADERS,
                allow_redirects=True
            )
            response.close()
            
            response_time = (time.time() - start_time) * 1000  # 毫秒
            
            result = {
                'response_time': response_time,
                'available': True,
                'status_code': response.status_code
            }
            
            self.success_count += 1
            
        except Exception as e:
            result = {
                'response_time': 9999,
                'available': False,
                'status_code': 0,
                'error': str(e)
            }
        
        # 缓存结果
        with self.lock:
            self.results_cache[cache_key] = result
        
        return result
    
    def calculate_score(self, test_result):
        """计算得分 - 基于响应时间，响应时间越短得分越高"""
        if not test_result['available']:
            return 0
        
        # 响应时间得分（响应时间越短得分越高）
        # 响应时间0-100ms得100分，100-500ms线性递减，500ms以上得0分
        response_time = test_result['response_time']
        if response_time <= 100:
            score = 100
        elif response_time <= 500:
            score = 100 - (response_time - 100) / 4  # 100-500ms线性递减
        else:
            score = 0
        
        return round(score, 2)
    
    def get_stats(self):
        """获取测试统计"""
        return {
            'total_tests': self.test_count,
            'successful_tests': self.success_count,
            'success_rate': round(self.success_count / max(self.test_count, 1) * 100, 2),
            'cache_size': len(self.results_cache)
        }

def clean_channel_name(name):
    """清理频道名称中的非法字符"""
    if not name or not isinstance(name, str):
        return "未知频道"
    return CHANNEL_NAME_CLEAN_PATTERN.sub('_', name).strip()

def load_local_sources():
    """加载本地源"""
    if not os.path.exists(LOCAL_SOURCE_FILE):
        print(f"📝 本地源文件 {LOCAL_SOURCE_FILE} 不存在，跳过")
        return []
    
    streams = []
    try:
        with open(LOCAL_SOURCE_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 支持多种格式
                if ',' in line:
                    parts = line.split(',', 1)
                    if len(parts) == 2 and parts[1].startswith(('http://', 'https://')):
                        program_name = clean_channel_name(parts[0].strip())
                        stream_url = parts[1].strip()
                        streams.append({
                            "program_name": program_name,
                            "stream_url": stream_url,
                            "source": "local"
                        })
                elif line.startswith(('http://', 'https://')):
                    program_name = f"本地频道_{line_num}"
                    streams.append({
                        "program_name": program_name,
                        "stream_url": line.strip(),
                        "source": "local"
                    })
    except Exception as e:
        print(f"❌ 读取本地源文件失败: {e}")
    
    print(f"✅ 从本地源加载了 {len(streams)} 个频道")
    return streams

def load_demo_template():
    """加载模板频道列表"""
    if not os.path.exists(DEMO_TEMPLATE_FILE):
        print(f"⚠️ 模板文件 {DEMO_TEMPLATE_FILE} 不存在，将按频道名排序")
        return []
    
    channels = []
    try:
        with open(DEMO_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    cleaned_name = clean_channel_name(line)
                    if cleaned_name and cleaned_name != "未知频道":
                        channels.append(cleaned_name)
    except Exception as e:
        print(f"❌ 读取模板文件失败: {e}")
    
    print(f"📋 从模板加载了 {len(channels)} 个频道")
    return channels

def fetch_streams_from_url(url):
    """从URL获取直播源数据"""
    print(f"🌐 正在爬取网站源: {url}")
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        content_length = len(response.content)
        print(f"✅ 成功获取 {url} 的数据 ({content_length} 字节)")
        return response.text
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求 {url} 时发生错误: {e}")
        return None

def fetch_online_sources(urls):
    """获取在线源"""
    if not urls:
        print("⚠️ 未提供在线源URL，跳过在线源获取")
        return []
    
    all_streams = []
    
    print("🚀 开始获取在线直播源...")
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(urls))) as executor:
        future_to_url = {executor.submit(fetch_streams_from_url, url): url for url in urls}
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                if content := future.result():
                    # 解析内容
                    if content.startswith("#EXTM3U"):
                        streams = parse_m3u(content)
                    else:
                        streams = parse_txt(content)
                    
                    # 标记来源并清理频道名
                    for stream in streams:
                        stream['source'] = 'online'
                        stream['program_name'] = clean_channel_name(stream['program_name'])
                    
                    all_streams.extend(streams)
                    print(f"📡 从 {url} 解析了 {len(streams)} 个频道")
            except Exception as e:
                print(f"❌ 处理 {url} 时发生错误: {e}")
    
    print(f"✅ 从在线源获取了 {len(all_streams)} 个频道")
    return all_streams

def parse_m3u(content):
    """解析M3U格式"""
    streams = []
    current_program = None
    
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("#EXTINF"):
            current_program = "未知频道"
            if match := EXTINF_PATTERN.search(line):
                current_program = match.group(1).strip()
            elif "," in line:
                current_program = line.split(",", 1)[1].strip()
            current_program = clean_channel_name(current_program)
                
        elif line.startswith(('http://', 'https://')):
            if current_program:
                streams.append({
                    "program_name": current_program,
                    "stream_url": line.strip()
                })
                current_program = None
                
    return streams

def parse_txt(content):
    """解析TXT格式"""
    streams = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # 尝试匹配 "频道名,URL" 格式
        if match := TXT_LINE_PATTERN.match(line):
            program_name = clean_channel_name(match.group(1).strip())
            stream_url = match.group(2).strip()
            
            streams.append({
                "program_name": program_name,
                "stream_url": stream_url
            })
        elif line.startswith(('http://', 'https://')):
            # 只有URL没有频道名的情况
            streams.append({
                "program_name": f"在线频道_{len(streams)}",
                "stream_url": line.strip()
            })
            
    return streams

def merge_and_deduplicate_sources(local_sources, online_sources):
    """合并并去重源"""
    all_sources = []
    seen_urls = set()
    
    # 优先添加本地源
    for source in local_sources:
        if source['stream_url'] not in seen_urls:
            all_sources.append(source)
            seen_urls.add(source['stream_url'])
    
    # 添加在线源（不重复的）
    for source in online_sources:
        if source['stream_url'] not in seen_urls:
            all_sources.append(source)
            seen_urls.add(source['stream_url'])
    
    print(f"🔄 合并后总频道数: {len(all_sources)} (本地: {len(local_sources)}, 在线: {len(online_sources)}, 去重: {len(local_sources) + len(online_sources) - len(all_sources)})")
    return all_sources

def group_by_channel(sources):
    """按频道名分组"""
    channels = {}
    
    for source in sources:
        program_name = source['program_name']
        if not program_name or program_name == "未知频道":
            continue
            
        if program_name not in channels:
            channels[program_name] = []
        
        channels[program_name].append({
            'url': source['stream_url'],
            'source': source.get('source', 'unknown')
        })
    
    return channels

def test_channel_urls(tester, program_name, urls):
    """测试频道的所有URL并排序"""
    if not urls:
        return []
    
    test_results = []
    
    print(f"🔍 测试频道 '{program_name}' 的 {len(urls)} 个源...")
    
    with ThreadPoolExecutor(max_workers=min(URL_TEST_WORKERS, len(urls))) as executor:
        future_to_url = {
            executor.submit(tester.test_stream, program_name, url_info['url']): url_info 
            for url_info in urls
        }
        
        for future in as_completed(future_to_url):
            url_info = future_to_url[future]
            try:
                test_result = future.result()
                score = tester.calculate_score(test_result)
                
                test_results.append({
                    'url': url_info['url'],
                    'source': url_info['source'],
                    'response_time': round(test_result['response_time'], 2),
                    'available': test_result['available'],
                    'score': score
                })
                
            except Exception as e:
                print(f"❌ 测试URL {url_info['url']} 时发生错误: {e}")
    
    # 按得分排序，过滤不可用的
    available_results = [r for r in test_results if r['available']]
    sorted_results = sorted(available_results, key=lambda x: x['score'], reverse=True)
    
    # 限制每个频道的URL数量
    final_results = sorted_results[:MAX_URLS_PER_CHANNEL]
    
    if final_results:
        best_time = final_results[0]['response_time']
        print(f"✅ {program_name}: 找到 {len(final_results)} 个可用源 (最佳响应: {best_time}ms)")
    else:
        print(f"❌ {program_name}: 无可用源")
    
    return final_results

def organize_channels_by_template(template_channels, tested_channels):
    """按照模板顺序整理频道"""
    organized = []
    missing_channels = []
    added_channels = set()
    
    # 按照模板顺序添加频道
    for channel_name in template_channels:
        if channel_name in tested_channels and tested_channels[channel_name]:
            channel_data = tested_channels[channel_name]
            organized.append({
                'program_name': channel_name,
                'streams': channel_data
            })
            added_channels.add(channel_name)
        else:
            missing_channels.append(channel_name)
    
    # 添加模板中没有但源中有的频道
    for channel_name, channel_data in tested_channels.items():
        if channel_name not in added_channels and channel_data:
            organized.append({
                'program_name': channel_name,
                'streams': channel_data
            })
    
    # 报告缺失频道
    if missing_channels:
        print(f"⚠️ 以下 {len(missing_channels)} 个模板频道未找到或无可用的源: {', '.join(missing_channels[:5])}{'...' if len(missing_channels) > 5 else ''}")
    
    return organized

def display_channel_stats(organized_channels, tester):
    """显示频道统计信息"""
    if not organized_channels:
        print("❌ 没有可用的频道数据")
        return
    
    print("\n" + "="*60)
    print("📊 频道统计报告")
    print("="*60)
    
    total_channels = len(organized_channels)
    total_streams = sum(len(channel['streams']) for channel in organized_channels)
    avg_streams_per_channel = round(total_streams / max(total_channels, 1), 2)
    
    # 统计源类型
    local_count = 0
    online_count = 0
    
    # 统计每个频道的接口数量
    channel_stream_counts = {}
    for channel in organized_channels:
        stream_count = len(channel['streams'])
        channel_stream_counts[channel['program_name']] = stream_count
    
    for channel in organized_channels:
        for stream in channel['streams']:
            if stream.get('source') == 'local':
                local_count += 1
            else:
                online_count += 1
    
    # 显示基本信息
    print(f"📺 总频道数: {total_channels}")
    print(f"🔗 总流媒体源: {total_streams}")
    print(f"📈 平均每个频道源数: {avg_streams_per_channel}")
    print(f"💾 本地源: {local_count}")
    print(f"🌍 在线源: {online_count}")
    
    # 显示测试统计
    test_stats = tester.get_stats()
    print(f"🧪 测试统计: {test_stats['successful_tests']}/{test_stats['total_tests']} 成功 ({test_stats['success_rate']}%)")
    
    # 显示频道接口数量分布
    print(f"\n📋 频道接口数量分布:")
    count_distribution = {}
    for count in channel_stream_counts.values():
        count_distribution[count] = count_distribution.get(count, 0) + 1
    
    for count in sorted(count_distribution.keys()):
        channel_count = count_distribution[count]
        print(f"  {count}个接口: {channel_count}个频道")
    
    print("="*60)

def save_to_txt(organized_channels, filename=OUTPUT_TXT_FILE):
    """保存为TXT格式，显示每个频道的接口数量"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            # 写入文件头信息
            f.write(f"# IPTV直播源列表\n")
            f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总频道数: {len(organized_channels)}\n")
            f.write(f"# 总接口数: {sum(len(channel['streams']) for channel in organized_channels)}\n\n")
            
            # 写入频道统计
            f.write("# 频道接口数量统计:\n")
            for channel in organized_channels:
                stream_count = len(channel['streams'])
                f.write(f"# {channel['program_name']}: {stream_count}个接口\n")
            f.write("\n")
            
            # 写入所有源
            all_streams = []
            
            for channel in organized_channels:
                for stream in channel['streams']:
                    line = f"{channel['program_name']},{stream['url']}"
                    all_streams.append(line)
            
            f.write("\n".join(all_streams))
        
        print(f"✅ 文本文件已保存: {os.path.abspath(filename)}")
        
        # 显示文件中的频道接口信息
        print(f"📋 生成的TXT文件中包含:")
        for channel in organized_channels:
            stream_count = len(channel['streams'])
            print(f"   {channel['program_name']}: {stream_count}个接口")
            
        return True
    except Exception as e:
        print(f"❌ 保存TXT文件失败: {e}")
        return False

def save_to_m3u(organized_channels, filename=OUTPUT_M3U_FILE):
    """保存为M3U格式，在注释中显示接口数量"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write(f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 总频道数: {len(organized_channels)}\n")
            f.write(f"# 总接口数: {sum(len(channel['streams']) for channel in organized_channels)}\n")
            
            # 写入频道统计
            f.write("# 频道接口数量统计:\n")
            for channel in organized_channels:
                stream_count = len(channel['streams'])
                f.write(f"# {channel['program_name']}: {stream_count}个接口\n")
            
            # 写入频道数据
            for channel in organized_channels:
                stream_count = len(channel['streams'])
                for i, stream in enumerate(channel['streams']):
                    # 在EXTINF行中添加接口序号信息
                    f.write(f'#EXTINF:-1 tvg-name="{channel["program_name"]}",{channel["program_name"]} [接口{i+1}/{stream_count}]\n')
                    f.write(f"{stream['url']}\n")
        
        print(f"✅ M3U文件已保存: {os.path.abspath(filename)}")
        
        # 显示文件中的频道接口信息
        print(f"📋 生成的M3U文件中包含:")
        for channel in organized_channels:
            stream_count = len(channel['streams'])
            print(f"   {channel['program_name']}: {stream_count}个接口")
            
        return True
    except Exception as e:
        print(f"❌ 保存M3U文件失败: {e}")
        return False

def create_sample_files():
    """创建示例文件"""
    # 创建本地源示例
    if not os.path.exists(LOCAL_SOURCE_FILE):
        sample_local = """# 本地直播源示例
# 格式: 频道名称,URL
CCTV-1,http://example.com/cctv1.m3u8
CCTV-2,http://example.com/cctv2.m3u8
湖南卫视,http://example.com/hunan.m3u8
浙江卫视,http://example.com/zhejiang.m3u8
"""
        with open(LOCAL_SOURCE_FILE, 'w', encoding='utf-8') as f:
            f.write(sample_local)
        print(f"📝 已创建示例本地源文件: {LOCAL_SOURCE_FILE}")
    
    # 创建模板示例
    if not os.path.exists(DEMO_TEMPLATE_FILE):
        sample_demo = """# 频道模板示例
# 每行一个频道名称，将按此顺序排列输出
CCTV-1
CCTV-2
湖南卫视
浙江卫视
江苏卫视
北京卫视
东方卫视
"""
        with open(DEMO_TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            f.write(sample_demo)
        print(f"📋 已创建示例模板文件: {DEMO_TEMPLATE_FILE}")

def main():
    """主函数"""
    print("🎬 IPTV直播源整理工具")
    print("=" * 50)
    
    # 创建示例文件（如果不存在）
    create_sample_files()
    
    start_time = time.time()
    
    # 初始化测试器
    tester = StreamTester()
    
    try:
        # 1. 加载本地源（优先）
        local_sources = load_local_sources()
        
        # 2. 加载在线源
        online_sources = fetch_online_sources(ONLINE_SOURCE_URLS)
        
        # 3. 合并源（本地源优先）
        all_sources = merge_and_deduplicate_sources(local_sources, online_sources)
        
        if not all_sources:
            print("❌ 错误: 没有找到任何直播源")
            return
        
        # 4. 按频道分组
        channel_groups = group_by_channel(all_sources)
        print(f"🔍 发现 {len(channel_groups)} 个唯一频道")
        
        if not channel_groups:
            print("❌ 错误: 没有有效的频道数据")
            return
        
        # 5. 测试所有频道的URL（不限制数量）
        print("\n🚀 开始测试所有频道源...")
        tested_channels = {}
        
        with ThreadPoolExecutor(max_workers=CHANNEL_TEST_WORKERS) as executor:
            future_to_channel = {
                executor.submit(test_channel_urls, tester, name, urls): name 
                for name, urls in channel_groups.items()
            }
            
            for future in as_completed(future_to_channel):
                channel_name = future_to_channel[future]
                try:
                    tested_urls = future.result()
                    if tested_urls:
                        tested_channels[channel_name] = tested_urls
                except Exception as e:
                    print(f"❌ 测试频道 {channel_name} 时发生错误: {e}")
        
        if not tested_channels:
            print("❌ 错误: 没有找到任何可用的直播源")
            return
        
        # 6. 按照模板排序
        template_channels = load_demo_template()
        organized_channels = organize_channels_by_template(template_channels, tested_channels)
        
        print(f"✅ 整理完成: {len(organized_channels)} 个频道")
        
        # 7. 显示统计信息
        display_channel_stats(organized_channels, tester)
        
        # 8. 保存文件
        success_txt = save_to_txt(organized_channels)
        success_m3u = save_to_m3u(organized_channels)
        
        total_time = time.time() - start_time
        
        if success_txt and success_m3u:
            print(f"\n🎉 处理完成! 总耗时: {total_time:.2f}秒")
            print(f"📁 输出文件: {OUTPUT_TXT_FILE}, {OUTPUT_M3U_FILE}")
            
            # 显示最终文件信息
            if os.path.exists(OUTPUT_TXT_FILE):
                file_size = os.path.getsize(OUTPUT_TXT_FILE)
                print(f"📄 {OUTPUT_TXT_FILE}: {file_size} 字节")
            if os.path.exists(OUTPUT_M3U_FILE):
                file_size = os.path.getsize(OUTPUT_M3U_FILE)
                print(f"📄 {OUTPUT_M3U_FILE}: {file_size} 字节")
        else:
            print(f"\n⚠️ 处理完成，但部分文件保存失败")
            
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断处理")
    except Exception as e:
        print(f"\n❌ 处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
