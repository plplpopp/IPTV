import requests
import re
import os
import time
import concurrent.futures
from tqdm import tqdm
import sys
import urllib3
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
MAX_WORKERS = 15

# ============================ 频道名称映射和规则 ============================
CHANNEL_MAPPING_RULES = {
    # CCTV频道映射
    'CCTV-1': ['CCTV1', 'CCTV-1', 'CCTV 1', '央视1套', '中央1套', 'CCTV1综合', '中央一套', '央视一套'],
    'CCTV-2': ['CCTV2', 'CCTV-2', 'CCTV 2', '央视2套', '中央2套', 'CCTV2财经', '中央二套', '央视二套'],
    'CCTV-3': ['CCTV3', 'CCTV-3', 'CCTV 3', '央视3套', '中央3套', 'CCTV3综艺', '中央三套', '央视三套'],
    'CCTV-4': ['CCTV4', 'CCTV-4', 'CCTV 4', '央视4套', '中央4套', 'CCTV4中文国际', '中央四套', '央视四套'],
    'CCTV-5': ['CCTV5', 'CCTV-5', 'CCTV 5', '央视5套', '中央5套', 'CCTV5体育', '中央五套', '央视五套'],
    'CCTV-5+': ['CCTV5+', 'CCTV5plus', 'CCTV-5+', 'CCTV5 Plus', '央视5+', 'CCTV5+体育赛事'],
    'CCTV-6': ['CCTV6', 'CCTV-6', 'CCTV 6', '央视6套', '中央6套', 'CCTV6电影', '中央六套', '央视六套'],
    'CCTV-7': ['CCTV7', 'CCTV-7', 'CCTV 7', '央视7套', '中央7套', 'CCTV7国防军事', '中央七套', '央视七套'],
    'CCTV-8': ['CCTV8', 'CCTV-8', 'CCTV 8', '央视8套', '中央8套', 'CCTV8电视剧', '中央八套', '央视八套'],
    'CCTV-9': ['CCTV9', 'CCTV-9', 'CCTV 9', '央视9套', '中央9套', 'CCTV9纪录', '中央九套', '央视九套'],
    'CCTV-10': ['CCTV10', 'CCTV-10', 'CCTV 10', '央视10套', '中央10套', 'CCTV10科教', '中央十套', '央视十套'],
    'CCTV-11': ['CCTV11', 'CCTV-11', 'CCTV 11', '央视11套', '中央11套', 'CCTV11戏曲', '中央十一套', '央视十一套'],
    'CCTV-12': ['CCTV12', 'CCTV-12', 'CCTV 12', '央视12套', '中央12套', 'CCTV12社会与法', '中央十二套', '央视十二套'],
    'CCTV-13': ['CCTV13', 'CCTV-13', 'CCTV 13', '央视13套', '中央13套', 'CCTV13新闻', '中央十三套', '央视十三套'],
    'CCTV-14': ['CCTV14', 'CCTV-14', 'CCTV 14', '央视14套', '中央14套', 'CCTV14少儿', '中央十四套', '央视十四套'],
    'CCTV-15': ['CCTV15', 'CCTV-15', 'CCTV 15', '央视15套', '中央15套', 'CCTV15音乐', '中央十五套', '央视十五套'],
    'CCTV-16': ['CCTV16', 'CCTV-16', 'CCTV 16', '央视16套', '中央16套', 'CCTV16奥林匹克', '中央十六套', '央视十六套'],
    'CCTV-17': ['CCTV17', 'CCTV-17', 'CCTV 17', '央视17套', '中央17套', 'CCTV17农业农村', '中央十七套', '央视十七套'],
    
    # 卫视频道映射
    '北京卫视': ['北京卫视', '北京电视台', 'BTV', '北京台', '北京卫视高清', 'BTV北京'],
    '湖南卫视': ['湖南卫视', '湖南电视台', 'HUNAN', '湖南台', '湖南卫视图标', 'HUNAN TV'],
    '浙江卫视': ['浙江卫视', '浙江电视台', 'ZHEJIANG', '浙江台', 'ZHEJIANG TV'],
    '江苏卫视': ['江苏卫视', '江苏电视台', 'JIANGSU', '江苏台', 'JIANGSU TV'],
    '东方卫视': ['东方卫视', '上海东方', 'DRAGON', '东方台', '上海东方卫视'],
    '安徽卫视': ['安徽卫视', '安徽电视台', 'ANHUI', '安徽台', 'ANHUI TV'],
    '广东卫视': ['广东卫视', '广东电视台', 'GUANGDONG', '广东台', 'GUANGDONG TV'],
    '深圳卫视': ['深圳卫视', '深圳电视台', 'SHENZHEN', '深圳台', 'SHENZHEN TV'],
    '山东卫视': ['山东卫视', '山东电视台', 'SHANDONG', '山东台', 'SHANDONG TV'],
    '天津卫视': ['天津卫视', '天津电视台', 'TIANJIN', '天津台', 'TIANJIN TV'],
    '湖北卫视': ['湖北卫视', '湖北电视台', 'HUBEI', '湖北台', 'HUBEI TV'],
    '四川卫视': ['四川卫视', '四川电视台', 'SICHUAN', '四川台', 'SICHUAN TV'],
    '辽宁卫视': ['辽宁卫视', '辽宁电视台', 'LIAONING', '辽宁台', 'LIAONING TV'],
    '河南卫视': ['河南卫视', '河南电视台', 'HENAN', '河南台', 'HENAN TV'],
    '重庆卫视': ['重庆卫视', '重庆电视台', 'CHONGQING', '重庆台', 'CHONGQING TV'],
    '黑龙江卫视': ['黑龙江卫视', '黑龙江电视台', 'HEILONGJIANG', '黑龙江台', 'HEILONGJIANG TV'],
    '河北卫视': ['河北卫视', '河北电视台', 'HEBEI', '河北台', 'HEBEI TV'],
    '吉林卫视': ['吉林卫视', '吉林电视台', 'JILIN', '吉林台', 'JILIN TV'],
    '陕西卫视': ['陕西卫视', '陕西电视台', 'SHAANXI', '陕西台', 'SHAANXI TV'],
    '山西卫视': ['山西卫视', '山西电视台', 'SHANXI', '山西台', 'SHANXI TV'],
    '甘肃卫视': ['甘肃卫视', '甘肃电视台', 'GANSU', '甘肃台', 'GANSU TV'],
    '青海卫视': ['青海卫视', '青海电视台', 'QINGHAI', '青海台', 'QINGHAI TV'],
    '福建卫视': ['福建卫视', '福建电视台', 'FUJIAN', '福建台', 'FUJIAN TV'],
    '江西卫视': ['江西卫视', '江西电视台', 'JIANGXI', '江西台', 'JIANGXI TV'],
    '广西卫视': ['广西卫视', '广西电视台', 'GUANGXI', '广西台', 'GUANGXI TV'],
    '贵州卫视': ['贵州卫视', '贵州电视台', 'GUIZHOU', '贵州台', 'GUIZHOU TV'],
    '云南卫视': ['云南卫视', '云南电视台', 'YUNNAN', '云南台', 'YUNNAN TV'],
    '内蒙古卫视': ['内蒙古卫视', '内蒙古电视台', 'NEIMENGGU', '内蒙古台', '内蒙古卫视汉语'],
    '新疆卫视': ['新疆卫视', '新疆电视台', 'XINJIANG', '新疆台', '新疆卫视汉语'],
    '西藏卫视': ['西藏卫视', '西藏电视台', 'XIZANG', '西藏台', '西藏卫视汉语'],
    '宁夏卫视': ['宁夏卫视', '宁夏电视台', 'NINGXIA', '宁夏台', 'NINGXIA TV'],
    '海南卫视': ['海南卫视', '海南电视台', 'HAINAN', '海南台', 'HAINAN TV'],
    
    # 其他频道
    '凤凰卫视': ['凤凰卫视', '凤凰中文', '凤凰台', 'FENG HUANG', '凤凰卫视图标', '凤凰卫视中文台'],
    '凤凰卫视香港': ['凤凰卫视香港', '凤凰香港', '凤凰卫视香港台'],
}

# ============================ 正则表达式 ============================
channel_pattern = re.compile(r"^([^,]+?),\s*(https?://.+)", re.IGNORECASE)
extinf_name_pattern = re.compile(r'#EXTINF:.*?,(.+)', re.IGNORECASE)

class IPTVProcessor:
    """IPTV处理器主类"""
    
    def __init__(self):
        self.channel_db = {}

    def create_correct_template(self):
        """创建正确的模板文件格式"""
        logger.info("📝 创建模板文件...")
        
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
            logger.info(f"✅ 创建模板文件: {TEMPLATE_FILE}")
            return True
        except Exception as e:
            logger.error(f"❌ 创建模板文件失败: {e}")
            return False

    def clean_channel_name(self, channel_name):
        """深度清理频道名称"""
        if not channel_name:
            return ""
        
        original_name = channel_name
        
        # 去除常见的后缀和质量标识
        suffixes = [
            '高清', '超清', '标清', 'HD', 'FHD', '4K', '8K', '直播', '频道', '卫视台', 
            '电视台', '台', 'CHANNEL', 'CCTV', '卫视', '综合', '源码', '稳定',
            '流畅', '秒开', '独家', '精品', '优质', '推荐', '最佳', '备用', '线路',
            '【', '】', '(', ')', '（', '）', '[', ']'
        ]
        
        # 去除括号内容（包括各种括号）
        cleaned_name = re.sub(r'[\(（\[【].*?[\)）\]】]', '', channel_name)
        
        # 去除质量标识
        quality_patterns = [
            r'\d{3,4}[PpXx]',  # 1080p, 720p等
            r'[Pp]高清',        # P高清
            r'[Hh]265',         # H265
            r'[Hh]264',         # H264
            r'[Aa][Vv][Cc]',    # AVC
            r'[Hh][Ee][Vv][Cc]', # HEVC
        ]
        
        for pattern in quality_patterns:
            cleaned_name = re.sub(pattern, '', cleaned_name)
        
        # 去除后缀词
        for suffix in suffixes:
            cleaned_name = cleaned_name.replace(suffix, '')
        
        # 标准化CCTV名称
        cctv_match = re.search(r'CCTV[\-\s]*(\d+\+?)', cleaned_name, re.IGNORECASE)
        if cctv_match:
            num = cctv_match.group(1)
            cleaned_name = f"CCTV-{num}" if '+' not in num else f"CCTV-{num}"
        
        # 标准化卫视名称
        if '卫视' not in cleaned_name and any(prov in cleaned_name for prov in 
            ['北京', '湖南', '浙江', '江苏', '东方', '安徽', '广东', '深圳', '山东', 
             '天津', '湖北', '四川', '辽宁', '河南', '重庆', '黑龙江', '河北', '吉林',
             '陕西', '山西', '甘肃', '青海', '福建', '江西', '广西', '贵州', '云南',
             '内蒙古', '新疆', '西藏', '宁夏', '海南']):
            cleaned_name = cleaned_name + '卫视'
        
        # 去除多余空格和特殊字符
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        cleaned_name = re.sub(r'[丨|·]', '', cleaned_name).strip()
        
        # 如果清理后为空，返回原始名称
        if not cleaned_name:
            return original_name.strip()
        
        return cleaned_name

    def load_template_channels(self):
        """加载模板频道列表"""
        if not os.path.exists(TEMPLATE_FILE):
            logger.error(f"❌ 模板文件 {TEMPLATE_FILE} 不存在")
            if not self.create_correct_template():
                return []
        
        template_channels = []
        
        try:
            logger.info(f"📁 加载模板文件: {TEMPLATE_FILE}")
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        template_channels.append(line)
            
            # 统计频道数量（仅用于信息显示）
            channel_count = len([line for line in template_channels if '#genre#' not in line and ',' not in line])
            logger.info(f"✅ 模板文件加载完成，共 {channel_count} 个频道")
            
            return template_channels
            
        except Exception as e:
            logger.error(f"❌ 加载模板文件失败: {e}")
            return []

    def load_local_sources(self):
        """优先加载本地源文件"""
        local_streams = []
        if not os.path.exists(LOCAL_SOURCE_FILE):
            logger.warning(f"⚠️  本地源文件 {LOCAL_SOURCE_FILE} 不存在，跳过")
            return local_streams
        
        try:
            logger.info(f"📁 加载本地源文件: {LOCAL_SOURCE_FILE}")
            with open(LOCAL_SOURCE_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 处理M3U格式
            if content.strip().startswith('#EXTM3U'):
                lines = content.splitlines()
                current_channel = None
                for line in lines:
                    line = line.strip()
                    if line.startswith('#EXTINF'):
                        # 提取频道名称
                        match = extinf_name_pattern.search(line)
                        if match:
                            current_channel = match.group(1).strip()
                    elif line and (line.startswith('http') or line.startswith('rtmp')) and current_channel:
                        local_streams.append(('local', f"{current_channel},{line}"))
                        current_channel = None
            else:
                # 处理普通格式
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        local_streams.append(('local', line))
                        
            logger.info(f"✅ 本地源文件加载完成，共 {len(local_streams)} 个流")
        except Exception as e:
            logger.error(f"❌ 加载本地源文件失败: {e}")
        
        return local_streams

    def fetch_online_sources(self):
        """抓取在线源数据"""
        online_streams = []
        
        def fetch_single_url(url):
            """获取单个URL的源数据"""
            try:
                logger.info(f"🌐 抓取: {url}")
                response = requests.get(url, timeout=25, verify=False)
                response.encoding = 'utf-8'
                if response.status_code == 200:
                    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
                    logger.info(f"✅ 成功抓取 {url}: {len(lines)} 行")
                    return (url, lines)
                else:
                    logger.error(f"❌ 抓取 {url} 失败，状态码: {response.status_code}")
                    return (url, [])
            except requests.exceptions.Timeout:
                logger.warning(f"⏰ 抓取 {url} 超时")
                return (url, [])
            except Exception as e:
                logger.error(f"❌ 抓取 {url} 失败: {str(e)[:100]}...")
                return (url, [])
        
        if not URL_SOURCES:
            logger.warning("⚠️  没有配置在线源URL")
            return online_streams
        
        logger.info("🌐 抓取在线源...")
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(URL_SOURCES), 6)) as executor:
                future_to_url = {executor.submit(fetch_single_url, url): url for url in URL_SOURCES}
                
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        source_url, result = future.result()
                        online_streams.extend([(source_url, line) for line in result])
                    except Exception as e:
                        logger.error(f"❌ 处理 {url} 时出错: {e}")
            
            logger.info(f"✅ 在线源抓取完成，共获取 {len(online_streams)} 行数据")
        except Exception as e:
            logger.error(f"❌ 抓取在线源时发生错误: {e}")
        
        return online_streams

    def parse_stream_line(self, source, line):
        """解析流数据行，提取频道名称和URL"""
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
            if len(parts) == 2 and (parts[1].startswith(('http://', 'https://', 'rtmp://'))):
                return (parts[0].strip(), parts[1].strip(), source)
        
        return None

    def build_complete_channel_database(self, local_streams, online_streams):
        """构建完整的频道数据库"""
        logger.info("📊 构建频道数据库...")
        channel_db = {}
        processed_count = 0
        
        all_streams = local_streams + online_streams
        
        # 用于去重的URL集合
        seen_urls = set()
        
        for source, line in all_streams:
            try:
                result = self.parse_stream_line(source, line)
                if result:
                    channel_name, url, source_info = result
                    
                    # URL去重
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    # 深度清理频道名称用于匹配
                    cleaned_name = self.clean_channel_name(channel_name)
                    
                    if cleaned_name and url:
                        if cleaned_name not in channel_db:
                            channel_db[cleaned_name] = []
                        
                        channel_db[cleaned_name].append((url, source_info, {}))
                        processed_count += 1
            except Exception as e:
                logger.warning(f"解析行失败: {line[:50]}... 错误: {e}")
        
        logger.info(f"✅ 频道数据库构建完成:")
        logger.info(f"  - 处理数据行: {processed_count}")
        logger.info(f"  - 唯一频道数: {len(channel_db)}")
        logger.info(f"  - 总流数量: {sum(len(urls) for urls in channel_db.values())}")
        
        return channel_db

    def comprehensive_speed_test(self, url):
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

    def speed_test_all_channels(self, channel_db):
        """对所有频道进行测速"""
        logger.info("🚀 开始全面测速...")
        
        total_urls = sum(len(urls) for urls in channel_db.values())
        logger.info(f"📊 需要测速的URL总数: {total_urls}")
        
        if total_urls == 0:
            logger.warning("⚠️  没有需要测速的URL，跳过测速步骤")
            return channel_db, {
                'total_tested': 0,
                'success_count': 0,
                'timeout_count': 0,
                'error_count': 0,
                'response_times': []
            }
        
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
        
        logger.info("⏱️  正在进行全面测速...")
        with tqdm(total=len(all_urls_to_test), desc="全面测速", unit="URL", 
                  bar_format='{l_bar}{bar:30}{r_bar}{bar:-30b}') as pbar:
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_url = {executor.submit(self.comprehensive_speed_test, url): url for url in all_urls_to_test}
                
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
                                        'score': self.calculate_stream_score(is_alive, response_time, download_speed)
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
                        logger.warning(f"测速处理失败: {e}")
                        pbar.update(1)
        
        if speed_stats['response_times']:
            avg_response_time = sum(speed_stats['response_times']) / len(speed_stats['response_times'])
        else:
            avg_response_time = 0
        
        logger.info(f"✅ 全面测速完成:")
        logger.info(f"  - 测试总数: {speed_stats['total_tested']}")
        logger.info(f"  - 成功: {speed_stats['success_count']} ({speed_stats['success_count']/speed_stats['total_tested']*100:.1f}%)")
        logger.info(f"  - 平均响应: {avg_response_time:.0f}ms")
        
        return channel_db, speed_stats

    def calculate_stream_score(self, is_alive, response_time, download_speed):
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

    def is_channel_match(self, template_channel, db_channel):
        """精准匹配频道名称，使用映射规则"""
        template_clean = self.clean_channel_name(template_channel)
        db_clean = self.clean_channel_name(db_channel)
        
        template_lower = template_clean.lower().strip()
        db_lower = db_clean.lower().strip()
        
        # 完全匹配
        if template_lower == db_lower:
            return True
        
        # 使用映射规则匹配
        for standard_name, variants in CHANNEL_MAPPING_RULES.items():
            standard_clean = self.clean_channel_name(standard_name).lower()
            
            # 如果模板频道在标准名称中
            if template_lower == standard_clean:
                # 检查数据库频道是否在变体列表中
                for variant in variants:
                    if db_lower == self.clean_channel_name(variant).lower():
                        return True
            
            # 如果数据库频道是标准名称
            if db_lower == standard_clean:
                # 检查模板频道是否在变体列表中
                for variant in variants:
                    if template_lower == self.clean_channel_name(variant).lower():
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
        if '卫视' in template_clean and '卫视' in db_clean:
            template_province = template_clean.replace('卫视', '').strip()
            db_province = db_clean.replace('卫视', '').strip()
            if template_province == db_province:
                return True
            # 处理简称匹配
            if template_province in db_province or db_province in template_province:
                return True
        
        # 其他频道的宽松匹配
        template_no_space = template_lower.replace(' ', '').replace('-', '')
        db_no_space = db_lower.replace(' ', '').replace('-', '')
        
        if template_no_space in db_no_space or db_no_space in template_no_space:
            similarity = len(set(template_no_space) & set(db_no_space)) / len(set(template_no_space) | set(db_no_space))
            if similarity > 0.7:  # 相似度阈值
                return True
        
        return False

    def find_matching_channels(self, template_channel, channel_db):
        """查找匹配的频道"""
        matched_urls = []
        
        for db_channel, urls in channel_db.items():
            if self.is_channel_match(template_channel, db_channel):
                valid_urls = [(url, source, info) for url, source, info in urls 
                            if info.get('alive', False)]
                matched_urls.extend(valid_urls)
        
        return matched_urls

    def match_template_channels(self, template_channels, channel_db):
        """匹配模板频道并选择最佳流"""
        logger.info("🎯 开始模板频道匹配...")
        
        txt_lines = []
        m3u_lines = ['#EXTM3U']
        current_group = "默认分组"
        matched_count = 0
        total_matched_streams = 0
        
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
                template_channel_for_match = self.clean_channel_name(line)
                
                logger.info(f"  🔍 查找频道: {template_channel_original}")
                
                matched_urls = self.find_matching_channels(template_channel_for_match, channel_db)
                
                if matched_urls:
                    matched_urls.sort(key=lambda x: x[2].get('score', 0), reverse=True)
                    best_urls = matched_urls[:MAX_STREAMS_PER_CHANNEL]
                    
                    for url, source, info in best_urls:
                        # 使用原始模板名称输出，确保显示完整的"CCTV-1"等名称
                        output_channel_name = template_channel_original.strip()
                        txt_lines.append(f"{output_channel_name},{url}")
                        m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{output_channel_name}')
                        m3u_lines.append(url)
                    
                    matched_count += 1
                    total_matched_streams += len(best_urls)
                    logger.info(f"  ✅ {template_channel_original}: 找到 {len(best_urls)} 个优质流")
                else:
                    logger.warning(f"  ❌ {template_channel_original}: 未找到有效流")
        
        try:
            with open(OUTPUT_TXT, 'w', encoding='utf-8') as f:
                f.write('\n'.join(txt_lines))
            logger.info(f"✅ 生成TXT文件: {OUTPUT_TXT}")
        except Exception as e:
            logger.error(f"❌ 写入TXT文件失败: {e}")
        
        try:
            with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
                f.write('\n'.join(m3u_lines))
            logger.info(f"✅ 生成M3U文件: {OUTPUT_M3U}")
        except Exception as e:
            logger.error(f"❌ 写入M3U文件失败: {e}")
        
        logger.info(f"🎯 模板匹配完成: {matched_count} 个频道匹配成功，共 {total_matched_streams} 个流")
        return matched_count

    def run(self):
        """运行主流程"""
        logger.info("🎬 IPTV频道整理工具开始运行...")
        start_time = time.time()
        
        try:
            # 1. 优先加载本地源
            logger.info("步骤1: 优先加载本地源")
            local_streams = self.load_local_sources()
            
            # 2. 抓取在线源
            logger.info("步骤2: 抓取在线源")
            online_streams = self.fetch_online_sources()
            
            # 3. 合并所有源构建完整数据库
            logger.info("步骤3: 合并所有源构建完整数据库")
            self.channel_db = self.build_complete_channel_database(local_streams, online_streams)
            
            if not self.channel_db:
                logger.error("❌ 无法构建频道数据库，停止执行")
                return False
            
            # 4. 对所有频道进行测速
            logger.info("步骤4: 全面测速和延时测试")
            self.channel_db, speed_stats = self.speed_test_all_channels(self.channel_db)
            
            # 5. 加载模板并进行匹配
            logger.info("步骤5: 模板频道匹配")
            template_channels = self.load_template_channels()
            if template_channels:
                matched_count = self.match_template_channels(template_channels, self.channel_db)
            else:
                logger.error("❌ 无法加载模板，跳过匹配")
                return False
            
            # 最终统计
            end_time = time.time()
            execution_time = round(end_time - start_time, 2)
            
            logger.info("🎉 执行完成!")
            logger.info(f"⏱️  总执行时间: {execution_time} 秒")
            logger.info(f"📺 总频道数: {len(self.channel_db)}")
            logger.info(f"✅ 有效流数量: {speed_stats['success_count']}")
            logger.info(f"🎯 模板匹配: {matched_count} 个频道")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 执行过程中发生错误: {e}")
            return False

def main():
    """主函数"""
    processor = IPTVProcessor()
    success = processor.run()
    
    if success:
        logger.info("✅ IPTV处理完成!")
        sys.exit(0)
    else:
        logger.error("❌ IPTV处理失败!")
        sys.exit(1)

if __name__ == "__main__":
    main()
