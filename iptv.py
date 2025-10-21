import requests
import pandas as pd
import re
import os
import time
import concurrent.futures
from urllib.parse import urlparse
from tqdm import tqdm
import sys
import subprocess
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

# 功能开关配置
CONFIG = {
    'ENABLE_BLACKLIST': True,           # 启用黑名单过滤
    'ENABLE_RESOLUTION_FILTER': True,   # 启用分辨率过滤
    'MIN_RESOLUTION': 720,              # 最低分辨率要求 (720p)
    'ENABLE_CVT_SOURCE': True,          # 启用.cvt源处理
    'ENABLE_FFMPEG_TEST': True,         # 启用FFmpeg测速 (需要安装FFmpeg)
    'ENABLE_SPEED_TEST': True,          # 启用常规测速
    'ENABLE_LOCAL_SOURCE': True,        # 启用本地源
    'ENABLE_ONLINE_SOURCE': True,       # 启用在线源
    'ENABLE_SPECIAL_FORMATS': True,     # 启用特殊格式支持
    'ENABLE_DIRECT_STREAM_TEST': True,  # 启用直接流测试
    'MAX_STREAMS_PER_CHANNEL': 8,       # 每个频道保留的接口数量
    'REQUEST_TIMEOUT': 10,              # 请求超时时间（秒）
    'SPEED_TEST_TIMEOUT': 15,           # 测速超时时间（秒）
    'FFMPEG_TIMEOUT': 25,               # FFmpeg测速超时时间（秒）
    'FFMPEG_TEST_DURATION': 10,         # FFmpeg测试时长（秒）
    'MAX_WORKERS': 15,                  # 最大线程数
}

# 特殊格式支持
SPECIAL_FORMATS = ['.ctv', '.cvt', '.m3u8', '.ts', '.flv', '.mpd']

# 文件配置
FILES = {
    'LOCAL_SOURCE_FILE': "local.txt",
    'BLACKLIST_FILE': "blacklist.txt",
    'TEMPLATE_FILE': "demo.txt",
    'OUTPUT_TXT': "iptv.txt",
    'OUTPUT_M3U': "iptv.m3u",
}

# ============================ 正则表达式 ============================
# IPv4地址匹配
ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')

# 频道名称和URL匹配
channel_pattern = re.compile(r"^([^,]+?),\s*(https?://.+)", re.IGNORECASE)

# M3U格式解析
extinf_pattern = re.compile(r'tvg-name="([^"]*)"', re.IGNORECASE)
extinf_name_pattern = re.compile(r'#EXTINF:.*?,(.+)', re.IGNORECASE)

# 分辨率匹配
resolution_pattern = re.compile(r'(\d{3,4})[x×*]?(\d{3,4})', re.IGNORECASE)

def load_blacklist():
    """加载黑名单关键词"""
    blacklist = []
    if not CONFIG['ENABLE_BLACKLIST']:
        print("⚙️  黑名单功能已禁用")
        return blacklist
        
    blacklist_file = FILES['BLACKLIST_FILE']
    if not os.path.exists(blacklist_file):
        print(f"⚠️  黑名单文件 {blacklist_file} 不存在，将创建示例文件")
        create_sample_blacklist()
        return blacklist
    
    try:
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            blacklist = [line.strip().lower() for line in f if line.strip() and not line.startswith('#')]
        print(f"✅ 加载黑名单: {len(blacklist)} 个关键词")
        if blacklist:
            print(f"   关键词示例: {', '.join(blacklist[:5])}")
    except Exception as e:
        print(f"❌ 加载黑名单失败: {e}")
    
    return blacklist

def create_sample_blacklist():
    """创建示例黑名单文件"""
    sample_content = """# 黑名单文件 - 每行一个关键词
# 符合这些关键词的频道或URL将被过滤

# 广告相关
advertisement
ad_
ads
推广
广告

# 低质量
low quality
bad quality
lag
卡顿

# 特定域名
example.com
bad-domain.com

# 其他不需要的内容
adult
赌博
"""
    try:
        with open(FILES['BLACKLIST_FILE'], 'w', encoding='utf-8') as f:
            f.write(sample_content)
        print(f"✅ 已创建示例黑名单文件: {FILES['BLACKLIST_FILE']}")
    except Exception as e:
        print(f"❌ 创建黑名单文件失败: {e}")

def is_blacklisted(channel_name, url, blacklist):
    """检查是否在黑名单中"""
    if not blacklist or not CONFIG['ENABLE_BLACKLIST']:
        return False
    
    combined_text = f"{channel_name} {url}".lower()
    
    for keyword in blacklist:
        if keyword in combined_text:
            print(f"🚫 黑名单过滤: {channel_name} - 关键词: {keyword}")
            return True
    
    return False

def detect_resolution_from_name(channel_name):
    """从频道名称中检测分辨率"""
    # 常见分辨率映射
    resolution_keywords = {
        '4k': 2160, 'uhd': 2160, 'ultra': 2160, '2160p': 2160,
        '1080p': 1080, '1080': 1080, 'fhd': 1080, 'fullhd': 1080,
        '720p': 720, '720': 720, 'hd': 720,
        '540p': 540, '540': 540,
        '480p': 480, '480': 480, 'sd': 480,
        '360p': 360, '360': 360
    }
    
    name_lower = channel_name.lower()
    
    # 检查分辨率关键词
    for keyword, resolution in resolution_keywords.items():
        if keyword in name_lower:
            return resolution
    
    # 尝试匹配数字分辨率
    match = resolution_pattern.search(channel_name)
    if match:
        width = int(match.group(1))
        height = int(match.group(2))
        return max(width, height)
    
    return None

def check_resolution_requirement(channel_name, detected_resolution):
    """检查分辨率是否符合要求"""
    if not CONFIG['ENABLE_RESOLUTION_FILTER']:
        return True
    
    min_resolution = CONFIG['MIN_RESOLUTION']
    
    if detected_resolution is None:
        # 无法检测分辨率时，默认保留
        return True
    
    if detected_resolution >= min_resolution:
        return True
    else:
        print(f"📺 分辨率过滤: {channel_name} - {detected_resolution}p < {min_resolution}p")
        return False

def handle_special_formats(url):
    """处理特殊格式的URL"""
    if not CONFIG['ENABLE_SPECIAL_FORMATS']:
        return url
    
    # 检查是否是特殊格式
    for format_ext in SPECIAL_FORMATS:
        if url.endswith(format_ext):
            print(f"🔧 检测到特殊格式: {format_ext} - {url}")
            
            # 对于.ctv/.cvt格式，可以添加特殊处理逻辑
            if format_ext in ['.ctv', '.cvt']:
                # 这里可以添加特殊格式的特殊处理
                # 例如：转换为其他格式或添加特定参数
                pass
                
    return url

def test_special_stream(url):
    """测试特殊格式的流媒体链接"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Origin': 'https://freetv.fun',
            'Referer': 'https://freetv.fun/'
        }
        
        start_time = time.time()
        
        # 对于特殊格式，使用GET请求测试
        response = requests.get(
            url, 
            timeout=CONFIG['REQUEST_TIMEOUT'],
            headers=headers,
            verify=False,
            stream=True
        )
        
        response_time = round((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            # 检查内容类型
            content_type = response.headers.get('content-type', '').lower()
            
            # 对于视频流，通常会有特定的content-type
            video_content_types = [
                'video/', 'application/vnd.apple.mpegurl', 
                'application/x-mpegurl', 'audio/mpegurl', 'application/dash+xml'
            ]
            
            is_video_stream = any(video_type in content_type for video_type in video_content_types)
            
            # 或者通过文件扩展名判断
            is_special_format = any(url.endswith(ext) for ext in SPECIAL_FORMATS)
            
            if is_video_stream or is_special_format:
                # 尝试读取一小部分数据来确认流可用性
                chunk_size = 1024 * 10  # 10KB
                downloaded = 0
                
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded >= chunk_size:
                            break
                
                response.close()
                return {
                    'alive': True,
                    'response_time': response_time,
                    'download_speed': None,  # 特殊格式不计算下载速度
                    'error': None,
                    'special_format': True,
                    'content_type': content_type
                }
            else:
                response.close()
                return {
                    'alive': False,
                    'response_time': response_time,
                    'download_speed': None,
                    'error': f"非视频流内容类型: {content_type}",
                    'special_format': False
                }
        else:
            response.close()
            return {
                'alive': False,
                'response_time': response_time,
                'download_speed': None,
                'error': f"HTTP {response.status_code}",
                'special_format': False
            }
            
    except requests.exceptions.Timeout:
        return {
            'alive': False,
            'response_time': None,
            'download_speed': None,
            'error': "连接超时",
            'special_format': False
        }
    except requests.exceptions.ConnectionError:
        return {
            'alive': False,
            'response_time': None,
            'download_speed': None,
            'error': "连接错误",
            'special_format': False
        }
    except Exception as e:
        return {
            'alive': False,
            'response_time': None,
            'download_speed': None,
            'error': f"测试错误: {str(e)[:50]}",
            'special_format': False
        }

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
        with open(FILES['TEMPLATE_FILE'], 'w', encoding='utf-8') as f:
            f.write(template_content)
        print(f"✅ 创建模板文件: {FILES['TEMPLATE_FILE']}")
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
    if not os.path.exists(FILES['TEMPLATE_FILE']):
        print(f"❌ 模板文件 {FILES['TEMPLATE_FILE']} 不存在")
        if not create_correct_template():
            return []
    
    template_channels = []
    template_channel_names = []  # 只存储频道名称
    
    try:
        print(f"📁 正在加载模板文件: {FILES['TEMPLATE_FILE']}")
        with open(FILES['TEMPLATE_FILE'], 'r', encoding='utf-8') as f:
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
    if not CONFIG['ENABLE_LOCAL_SOURCE']:
        print("⚙️  本地源功能已禁用")
        return local_streams
        
    if not os.path.exists(FILES['LOCAL_SOURCE_FILE']):
        print(f"⚠️  本地源文件 {FILES['LOCAL_SOURCE_FILE']} 不存在，跳过")
        return local_streams
    
    try:
        print(f"📁 正在优先加载本地源文件: {FILES['LOCAL_SOURCE_FILE']}")
        with open(FILES['LOCAL_SOURCE_FILE'], 'r', encoding='utf-8') as f:
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
    
    if not CONFIG['ENABLE_ONLINE_SOURCE']:
        print("⚙️  在线源功能已禁用")
        return online_streams
    
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

def parse_stream_line(source, line, blacklist):
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
        
        # 特殊格式处理
        if CONFIG['ENABLE_SPECIAL_FORMATS']:
            url = handle_special_formats(url)
        
        # 黑名单检查
        if is_blacklisted(channel_name, url, blacklist):
            return None
        
        # 分辨率检查
        detected_resolution = detect_resolution_from_name(channel_name)
        if not check_resolution_requirement(channel_name, detected_resolution):
            return None
            
        # .cvt源处理
        if CONFIG['ENABLE_CVT_SOURCE'] and url.endswith('.cvt'):
            print(f"🔧 发现.cvt源: {channel_name}")
        
        return (channel_name, url, source, detected_resolution)
    
    # 尝试其他可能的格式
    if ',' in line:
        parts = line.split(',', 1)
        if len(parts) == 2 and parts[1].startswith(('http://', 'https://')):
            channel_name = parts[0].strip()
            url = parts[1].strip()
            
            # 特殊格式处理
            if CONFIG['ENABLE_SPECIAL_FORMATS']:
                url = handle_special_formats(url)
            
            # 黑名单检查
            if is_blacklisted(channel_name, url, blacklist):
                return None
            
            # 分辨率检查
            detected_resolution = detect_resolution_from_name(channel_name)
            if not check_resolution_requirement(channel_name, detected_resolution):
                return None
                
            return (channel_name, url, source, detected_resolution)
    
    return None

def build_complete_channel_database(local_streams, online_streams, blacklist):
    """构建完整的频道数据库"""
    print("📊 正在构建完整频道数据库...")
    channel_db = {}
    processed_count = 0
    filtered_count = 0
    
    all_streams = local_streams + online_streams
    
    for source, line in all_streams:
        result = parse_stream_line(source, line, blacklist)
        if result:
            channel_name, url, source_info, resolution = result
            # 清理频道名称用于匹配
            cleaned_name = clean_channel_name(channel_name)
            
            if cleaned_name not in channel_db:
                channel_db[cleaned_name] = []
            
            if not any(existing_url == url for existing_url, _, _, _ in channel_db[cleaned_name]):
                channel_db[cleaned_name].append((url, source_info, resolution, {}))
            processed_count += 1
        else:
            filtered_count += 1
    
    print(f"✅ 完整频道数据库构建完成:")
    print(f"  - 处理数据行: {processed_count + filtered_count}")
    print(f"  - 过滤数据行: {filtered_count}")
    print(f"  - 有效数据行: {processed_count}")
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

def ffmpeg_speed_test(url):
    """使用FFmpeg进行测速 - 测试10秒"""
    if not CONFIG['ENABLE_FFMPEG_TEST']:
        return None, None, "FFmpeg测试已禁用"
    
    try:
        # 检查FFmpeg是否可用
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode != 0:
            return None, None, "FFmpeg未安装或不可用"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        return None, None, f"FFmpeg检查失败: {str(e)}"
    
    try:
        start_time = time.time()
        
        # 使用FFmpeg测试流（测试10秒）
        test_duration = CONFIG['FFMPEG_TEST_DURATION']
        cmd = [
            'ffmpeg',
            '-i', url,
            '-t', str(test_duration),  # 测试10秒
            '-f', 'null', '-',
            '-y'  # 覆盖输出文件
        ]
        
        print(f"🎬 FFmpeg测试 {url} - 时长: {test_duration}秒")
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            timeout=CONFIG['FFMPEG_TIMEOUT'],
            text=True
        )
        
        end_time = time.time()
        total_time = round((end_time - start_time) * 1000)
        
        # 解析FFmpeg输出获取信息
        output = result.stderr
        
        # 检查是否成功连接
        if "Connection refused" in output:
            return False, total_time, "连接被拒绝"
        if "Failed to resolve" in output:
            return False, total_time, "域名解析失败"
        if "Server returned 4" in output or "HTTP error" in output:
            return False, total_time, "HTTP错误"
        
        # 检查是否有视频流
        if "Video:" in output:
            # 尝试解析分辨率
            video_match = re.search(r'Video:.*?(\d+)x(\d+)', output)
            if video_match:
                width = int(video_match.group(1))
                height = int(video_match.group(2))
                resolution = max(width, height)
            else:
                resolution = None
            
            # 尝试解析码率
            bitrate_match = re.search(r'bitrate:\s*(\d+)\s*kb/s', output)
            bitrate = bitrate_match.group(1) if bitrate_match else "未知"
            
            # 尝试解析帧率
            fps_match = re.search(r'(\d+(?:\.\d+)?)\s*fps', output)
            fps = fps_match.group(1) if fps_match else "未知"
            
            success_msg = f"FFmpeg测试成功 ({test_duration}秒)"
            if resolution:
                success_msg += f" - 分辨率: {resolution}p"
            if bitrate != "未知":
                success_msg += f" - 码率: {bitrate}kb/s"
            if fps != "未知":
                success_msg += f" - 帧率: {fps}fps"
                
            return True, total_time, success_msg
        else:
            return False, total_time, "无视频流"
            
    except subprocess.TimeoutExpired:
        return False, None, f"FFmpeg测试超时 ({CONFIG['FFMPEG_TIMEOUT']}秒)"
    except Exception as e:
        return False, None, f"FFmpeg错误: {str(e)[:50]}"

def comprehensive_speed_test(url):
    """全面测速功能"""
    speed_info = {}
    
    # 检查是否是特殊格式
    is_special_format = any(url.endswith(ext) for ext in SPECIAL_FORMATS)
    
    if is_special_format and CONFIG['ENABLE_DIRECT_STREAM_TEST']:
        print(f"🎯 测试特殊格式流: {url}")
        return test_special_stream(url)
    
    # 常规HTTP测速
    if CONFIG['ENABLE_SPEED_TEST']:
        try:
            start_time = time.time()
            response = requests.head(url, timeout=CONFIG['REQUEST_TIMEOUT'], verify=False, 
                                   headers={'User-Agent': 'Mozilla/5.0'})
            head_time = time.time()
            response_time_ms = round((head_time - start_time) * 1000)
            
            if response.status_code != 200:
                speed_info.update({
                    'alive': False,
                    'response_time': response_time_ms,
                    'error': f"HTTP {response.status_code}"
                })
                return speed_info
            
            download_speed = None
            try:
                chunk_size = 1024 * 50
                start_download = time.time()
                download_response = requests.get(url, timeout=CONFIG['SPEED_TEST_TIMEOUT'], 
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
            
            speed_info.update({
                'alive': True,
                'response_time': response_time_ms,
                'download_speed': download_speed,
                'error': None
            })
            
        except requests.exceptions.Timeout:
            speed_info.update({
                'alive': False,
                'response_time': None,
                'download_speed': None,
                'error': "Timeout"
            })
        except requests.exceptions.ConnectionError:
            speed_info.update({
                'alive': False, 
                'response_time': None,
                'download_speed': None,
                'error': "Connection Error"
            })
        except Exception as e:
            speed_info.update({
                'alive': False,
                'response_time': None, 
                'download_speed': None,
                'error': str(e)[:50]
            })
    
    # FFmpeg测速 - 只有在常规测试成功时才进行
    if CONFIG['ENABLE_FFMPEG_TEST'] and speed_info.get('alive', False):
        print(f"🔍 进行FFmpeg深度测试: {url}")
        ffmpeg_alive, ffmpeg_response_time, ffmpeg_error = ffmpeg_speed_test(url)
        speed_info.update({
            'ffmpeg_alive': ffmpeg_alive,
            'ffmpeg_response_time': ffmpeg_response_time,
            'ffmpeg_error': ffmpeg_error
        })
        
        # 如果FFmpeg测试失败，但常规测试成功，降低评分
        if not ffmpeg_alive:
            print(f"⚠️  FFmpeg测试失败但常规测试成功: {url}")
    
    # 计算综合评分
    speed_info['score'] = calculate_stream_score(speed_info)
    
    return speed_info

def calculate_stream_score(speed_info):
    """计算流质量综合评分"""
    if not speed_info.get('alive', False):
        return 0
    
    score = 0
    
    # 响应时间评分
    response_time = speed_info.get('response_time')
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
    
    # 下载速度评分
    download_speed = speed_info.get('download_speed')
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
    
    # FFmpeg测试加分（重要权重）
    if speed_info.get('ffmpeg_alive'):
        score += 30  # 增加FFmpeg测试的权重
        # FFmpeg响应时间也考虑
        ffmpeg_time = speed_info.get('ffmpeg_response_time')
        if ffmpeg_time and ffmpeg_time <= 5000:  # 5秒内完成测试
            score += 10
    else:
        # FFmpeg测试失败但常规测试成功，适当扣分
        if speed_info.get('alive'):
            score -= 15
    
    # 特殊格式流加分
    if speed_info.get('special_format'):
        score += 15
    
    return max(0, score)  # 确保分数不为负

def speed_test_all_channels(channel_db):
    """对所有频道进行测速"""
    print("\n🚀 开始全面测速...")
    
    total_urls = sum(len(urls) for urls in channel_db.values())
    print(f"📊 需要测速的URL总数: {total_urls}")
    
    # 如果启用FFmpeg测试，显示提示
    if CONFIG['ENABLE_FFMPEG_TEST']:
        print(f"🎬 FFmpeg测速已启用 - 每个流测试{CONFIG['FFMPEG_TEST_DURATION']}秒")
        print("⚠️  注意: FFmpeg测速会显著增加测试时间，但结果更准确")
    
    all_urls_to_test = []
    url_to_channel_map = {}
    
    for channel_name, urls in channel_db.items():
        for url, source, resolution, _ in urls:
            all_urls_to_test.append(url)
            url_to_channel_map[url] = channel_name
    
    speed_stats = {
        'total_tested': 0,
        'success_count': 0,
        'timeout_count': 0,
        'error_count': 0,
        'ffmpeg_success_count': 0,
        'ffmpeg_fail_count': 0,
        'response_times': []
    }
    
    print("⏱️  正在进行全面测速...")
    with tqdm(total=len(all_urls_to_test), desc="全面测速", unit="URL", 
              bar_format='{l_bar}{bar:30}{r_bar}{bar:-30b}') as pbar:
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG['MAX_WORKERS']) as executor:
            future_to_url = {executor.submit(comprehensive_speed_test, url): url for url in all_urls_to_test}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                channel_name = url_to_channel_map[url]
                
                try:
                    speed_info = future.result()
                    speed_stats['total_tested'] += 1
                    
                    for i, (stream_url, source, resolution, _) in enumerate(channel_db[channel_name]):
                        if stream_url == url:
                            channel_db[channel_name][i] = (
                                stream_url, 
                                source, 
                                resolution,
                                speed_info
                            )
                            break
                    
                    if speed_info.get('alive', False):
                        speed_stats['success_count'] += 1
                        response_time = speed_info.get('response_time')
                        if response_time:
                            speed_stats['response_times'].append(response_time)
                        
                        # FFmpeg统计
                        if speed_info.get('ffmpeg_alive'):
                            speed_stats['ffmpeg_success_count'] += 1
                        elif CONFIG['ENABLE_FFMPEG_TEST']:
                            speed_stats['ffmpeg_fail_count'] += 1
                    else:
                        if speed_info.get('error') == "Timeout":
                            speed_stats['timeout_count'] += 1
                        else:
                            speed_stats['error_count'] += 1
                    
                    # 更新进度条显示
                    postfix_info = {
                        'success': f"{speed_stats['success_count']}/{speed_stats['total_tested']}",
                    }
                    if speed_stats['response_times']:
                        postfix_info['avg_time'] = f"{sum(speed_stats['response_times'])/len(speed_stats['response_times']):.0f}ms"
                    if CONFIG['ENABLE_FFMPEG_TEST']:
                        postfix_info['ffmpeg'] = f"{speed_stats['ffmpeg_success_count']}PASS"
                    
                    pbar.set_postfix(**postfix_info)
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
    if CONFIG['ENABLE_FFMPEG_TEST']:
        print(f"  - FFmpeg测试成功: {speed_stats['ffmpeg_success_count']}")
        print(f"  - FFmpeg测试失败: {speed_stats['ffmpeg_fail_count']}")
    print(f"  - 平均响应: {avg_response_time:.0f}ms")
    print(f"  - 最快响应: {min_response_time}ms")
    print(f"  - 最慢响应: {max_response_time}ms")
    
    return channel_db, speed_stats

def is_exact_channel_match(template_channel, db_channel):
    """
    精准匹配频道名称 - 只进行完全匹配
    """
    template_clean = clean_channel_name(template_channel)
    db_clean = clean_channel_name(db_channel)
    
    # 完全匹配
    return template_clean == db_clean

def find_matching_channels(template_channel, channel_db):
    """查找精准匹配的频道"""
    matched_urls = []
    
    for db_channel, urls in channel_db.items():
        if is_exact_channel_match(template_channel, db_channel):
            valid_urls = [(url, source, resolution, info) for url, source, resolution, info in urls 
                        if info.get('alive', False)]
            matched_urls.extend(valid_urls)
    
    return matched_urls

def match_template_channels(template_channels, channel_db):
    """匹配模板频道并选择最佳流"""
    print("\n🎯 开始模板频道精准匹配...")
    
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
            
            print(f"  🔍 精准查找频道: {template_channel_original}")
            
            matched_urls = find_matching_channels(template_channel_original, channel_db)
            
            if matched_urls:
                matched_urls.sort(key=lambda x: x[3].get('score', 0), reverse=True)
                best_urls = matched_urls[:CONFIG['MAX_STREAMS_PER_CHANNEL']]
                
                for url, source, resolution, info in best_urls:
                    # 使用原始模板名称输出，确保显示完整的标准名称
                    output_channel_name = format_channel_name_for_output(template_channel_original)
                    
                    # 添加分辨率信息到频道名称（不添加✅标记）
                    if resolution and CONFIG['ENABLE_RESOLUTION_FILTER']:
                        output_channel_name = f"{output_channel_name}({resolution}p)"
                    
                    txt_lines.append(f"{output_channel_name},{url}")
                    m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{output_channel_name}')
                    m3u_lines.append(url)
                
                matched_count += 1
                print(f"  ✅ {template_channel_original}: 找到 {len(best_urls)} 个精准匹配的优质流")
            else:
                print(f"  ❌ {template_channel_original}: 未找到精准匹配的有效流")
    
    try:
        with open(FILES['OUTPUT_TXT'], 'w', encoding='utf-8') as f:
            f.write('\n'.join(txt_lines))
        print(f"✅ 生成TXT文件: {FILES['OUTPUT_TXT']}，共 {len(txt_lines)} 行")
    except Exception as e:
        print(f"❌ 写入TXT文件失败: {e}")
    
    try:
        with open(FILES['OUTPUT_M3U'], 'w', encoding='utf-8') as f:
            f.write('\n'.join(m3u_lines))
        print(f"✅ 生成M3U文件: {FILES['OUTPUT_M3U']}，共 {len(m3u_lines)} 行")
    except Exception as e:
        print(f"❌ 写入M3U文件失败: {e}")
    
    print(f"🎯 模板精准匹配完成: {matched_count} 个频道匹配成功")
    return matched_count

def print_config_summary():
    """打印配置摘要"""
    print("⚙️  当前配置:")
    print(f"  - 黑名单过滤: {'✅' if CONFIG['ENABLE_BLACKLIST'] else '❌'}")
    print(f"  - 分辨率过滤: {'✅' if CONFIG['ENABLE_RESOLUTION_FILTER'] else '❌'} (最低{CONFIG['MIN_RESOLUTION']}p)")
    print(f"  - .cvt源处理: {'✅' if CONFIG['ENABLE_CVT_SOURCE'] else '❌'}")
    print(f"  - FFmpeg测速: {'✅' if CONFIG['ENABLE_FFMPEG_TEST'] else '❌'} (测试{CONFIG['FFMPEG_TEST_DURATION']}秒)")
    print(f"  - 常规测速: {'✅' if CONFIG['ENABLE_SPEED_TEST'] else '❌'}")
    print(f"  - 特殊格式支持: {'✅' if CONFIG['ENABLE_SPECIAL_FORMATS'] else '❌'}")
    print(f"  - 直接流测试: {'✅' if CONFIG['ENABLE_DIRECT_STREAM_TEST'] else '❌'}")
    print(f"  - 本地源: {'✅' if CONFIG['ENABLE_LOCAL_SOURCE'] else '❌'}")
    print(f"  - 在线源: {'✅' if CONFIG['ENABLE_ONLINE_SOURCE'] else '❌'}")
    print(f"  - 精准匹配: ✅ (已启用)")
    print(f"  - 每频道最大流数: {CONFIG['MAX_STREAMS_PER_CHANNEL']}")
    print(f"  - 最大线程数: {CONFIG['MAX_WORKERS']}")

def test_freetv_ctv_stream():
    """专门测试freetv的.ctv流"""
    test_url = "https://stream1.freetv.fun/cctv4-zhong-wen-guo-ji-1.ctv"
    
    print(f"\n🔍 测试特定流: {test_url}")
    
    # 方法1: 直接HTTP请求测试
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(test_url, headers=headers, timeout=10, stream=True, verify=False)
        print(f"📡 响应状态: {response.status_code}")
        print(f"📦 内容类型: {response.headers.get('content-type')}")
        print(f"📏 内容长度: {response.headers.get('content-length')}")
        
        # 尝试读取前几个字节
        chunk = response.raw.read(100)
        print(f"🔢 前100字节: {chunk[:20]}...")
        
        response.close()
        
        # 如果启用FFmpeg，也进行FFmpeg测试
        if CONFIG['ENABLE_FFMPEG_TEST']:
            print(f"🎬 进行FFmpeg深度测试...")
            ffmpeg_alive, ffmpeg_time, ffmpeg_msg = ffmpeg_speed_test(test_url)
            print(f"FFmpeg结果: {'通过' if ffmpeg_alive else '失败'} - {ffmpeg_msg}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def main():
    """主函数"""
    print("🎬 IPTV频道整理工具开始运行...")
    start_time = time.time()
    
    # 打印配置摘要
    print_config_summary()
    
    # 测试特定流（可选）
    if CONFIG['ENABLE_SPECIAL_FORMATS']:
        test_freetv_ctv_stream()
    
    # 1. 加载黑名单
    print("\n" + "="*50)
    print("步骤1: 加载黑名单")
    blacklist = load_blacklist()
    
    # 2. 优先加载本地源
    print("\n" + "="*50)
    print("步骤2: 优先加载本地源")
    local_streams = load_local_sources()
    
    # 3. 抓取在线源
    print("\n" + "="*50)
    print("步骤3: 抓取在线源")
    online_streams = fetch_online_sources()
    
    # 4. 合并所有源构建完整数据库
    print("\n" + "="*50)
    print("步骤4: 合并所有源构建完整数据库")
    channel_db = build_complete_channel_database(local_streams, online_streams, blacklist)
    
    if not channel_db:
        print("❌ 没有有效的频道数据，程序退出")
        return
    
    # 5. 对所有频道进行测速
    print("\n" + "="*50)
    print("步骤5: 全面测速和延时测试")
    channel_db, speed_stats = speed_test_all_channels(channel_db)
    
    # 6. 加载模板并进行匹配
    print("\n" + "="*50)
    print("步骤6: 模板频道精准匹配")
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
    if CONFIG['ENABLE_FFMPEG_TEST']:
        print(f"  🎬 FFmpeg验证成功: {speed_stats['ffmpeg_success_count']}")
    print(f"  🎯 精准匹配: {matched_count} 个频道")
    if speed_stats['response_times']:
        print(f"  📈 平均响应: {sum(speed_stats['response_times'])/len(speed_stats['response_times']):.0f}ms")
    print(f"\n📁 输出文件:")
    print(f"  - {FILES['OUTPUT_TXT']} (频道列表)")
    print(f"  - {FILES['OUTPUT_M3U']} (M3U播放列表)")
    print("="*60)

if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()
    main()
