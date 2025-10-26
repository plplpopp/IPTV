import requests
import pandas as pd
import re
import os
import time
import subprocess
import threading
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

class IPTVCrawler:
    def __init__(self):
        # 集中配置 - 所有设置都在这里
        self.config = {
            # FFmpeg测速配置
            'ffmpeg_enabled': True,           # FFmpeg测速总开关
            'ffmpeg_timeout': 10,             # 测速超时时间（秒）
            'ffmpeg_max_workers': 5,          # 最大并发测速数
            'ffmpeg_speed_weight': 0.5,       # 速度权重
            'ffmpeg_response_weight': 0.5,    # 响应时间权重
            
            # 数据源配置
            'local_sources_enabled': True,    # 本地源开关
            'network_sources_enabled': True,  # 网络源开关
            
            # 过滤配置
            'blacklist_enabled': True,        # 黑名单开关
            'alias_enabled': True,            # 别名映射开关
            'demo_template_enabled': True,    # 模板频道开关
            
            # 输出配置
            'max_urls_per_channel': 8,        # 每个频道最大源数量
            'save_txt_enabled': True,         # 保存TXT文件开关
            'save_m3u_enabled': True,         # 保存M3U文件开关
        }
        
        # 数据源
        self.urls = [
            "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
            "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
            "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",  
            "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
            "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
            "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
            "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
            "http://47.120.41.246:8899/zb.txt",
        ]
        
        self.local_file = "local.txt"
        self.blacklist_file = "blacklist.txt"
        self.alias_file = "alias.txt"
        self.demo_file = "demo.txt"
        
        # 正则表达式
        self.ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')
        self.ipv6_pattern = re.compile(r'^https?://\[([a-fA-F0-9:]+)\]')
        
        # 会话设置
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 加载数据文件
        self.blacklist = self.load_blacklist() if self.config['blacklist_enabled'] else {'keywords': [], 'domains': [], 'ips': []}
        self.alias_mapping = self.load_alias_mapping() if self.config['alias_enabled'] else {}
        self.demo_structure = self.load_demo_structure() if self.config['demo_template_enabled'] else {'categories': [], 'channels': {}}
        
        # 显示当前配置
        self.show_config()

    def show_config(self):
        """显示当前配置"""
        print("🎛️  当前配置:")
        print(f"  FFmpeg测速: {'✅ 开启' if self.config['ffmpeg_enabled'] else '❌ 关闭'}")
        print(f"  测速超时: {self.config['ffmpeg_timeout']}秒")
        print(f"  最大并发: {self.config['ffmpeg_max_workers']}")
        print(f"  速度权重: {self.config['ffmpeg_speed_weight']}")
        print(f"  响应权重: {self.config['ffmpeg_response_weight']}")
        print(f"  本地源: {'✅ 开启' if self.config['local_sources_enabled'] else '❌ 关闭'}")
        print(f"  网络源: {'✅ 开启' if self.config['network_sources_enabled'] else '❌ 关闭'}")
        print(f"  黑名单: {'✅ 开启' if self.config['blacklist_enabled'] else '❌ 关闭'}")
        print(f"  别名映射: {'✅ 开启' if self.config['alias_enabled'] else '❌ 关闭'}")
        print(f"  模板频道: {'✅ 开启' if self.config['demo_template_enabled'] else '❌ 关闭'}")
        print(f"  每频道最大源: {self.config['max_urls_per_channel']}")
        print(f"  保存TXT: {'✅ 开启' if self.config['save_txt_enabled'] else '❌ 关闭'}")
        print(f"  保存M3U: {'✅ 开启' if self.config['save_m3u_enabled'] else '❌ 关闭'}")
        print()

    def test_stream_with_ffmpeg(self, stream_url):
        """使用FFmpeg测试流媒体速度和响应时间"""
        if not self.config['ffmpeg_enabled']:
            return {'speed_score': 0.5, 'response_time': 0.5, 'status': 'disabled'}
            
        try:
            # 构建FFmpeg命令
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-t', '5',  # 测试5秒
                '-f', 'null',  # 输出为空
                '-',  # 输出到stdout
                '-hide_banner',
                '-loglevel', 'error'
            ]
            
            start_time = time.time()
            
            # 执行FFmpeg命令
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL
            )
            
            # 等待进程完成或超时
            try:
                _, stderr = process.communicate(timeout=self.config['ffmpeg_timeout'])
                response_time = time.time() - start_time
                
                # 解析FFmpeg输出获取速度信息
                stderr_text = stderr.decode('utf-8', errors='ignore')
                
                # 计算速度得分（基于比特率）
                speed_score = 0.1  # 默认得分
                if 'bitrate=' in stderr_text:
                    # 提取比特率信息
                    bitrate_match = re.search(r'bitrate=\s*([\d.]+)\s*kb/s', stderr_text)
                    if bitrate_match:
                        bitrate = float(bitrate_match.group(1))
                        # 比特率越高得分越高，最大2Mbps为满分
                        speed_score = min(bitrate / 2000, 1.0)
                
                # 计算响应时间得分（响应时间越短得分越高）
                response_score = max(0, 1 - (response_time / self.config['ffmpeg_timeout']))
                
                # 综合得分
                total_score = (
                    speed_score * self.config['ffmpeg_speed_weight'] +
                    response_score * self.config['ffmpeg_response_weight']
                )
                
                return {
                    'speed_score': speed_score,
                    'response_time': response_time,
                    'response_score': response_score,
                    'total_score': total_score,
                    'status': 'success'
                }
                
            except subprocess.TimeoutExpired:
                process.kill()
                return {'speed_score': 0, 'response_time': self.config['ffmpeg_timeout'], 'response_score': 0, 'total_score': 0, 'status': 'timeout'}
                
        except Exception as e:
            return {'speed_score': 0, 'response_time': 0, 'response_score': 0, 'total_score': 0, 'status': f'error: {str(e)}'}

    def test_streams_batch(self, stream_urls):
        """批量测试流媒体"""
        if not self.config['ffmpeg_enabled']:
            return {url: {'total_score': 0.5} for url in stream_urls}
            
        results = {}
        print(f"🔍 开始FFmpeg测速，共 {len(stream_urls)} 个源，最大并发 {self.config['ffmpeg_max_workers']}")
        
        with ThreadPoolExecutor(max_workers=self.config['ffmpeg_max_workers']) as executor:
            future_to_url = {executor.submit(self.test_stream_with_ffmpeg, url): url for url in stream_urls}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    results[url] = result
                    
                    status_icons = {
                        'success': '✅',
                        'timeout': '⏰',
                        'disabled': '⚪',
                        'error': '❌'
                    }
                    
                    icon = status_icons.get(result['status'], '❓')
                    if result['status'] == 'success':
                        print(f"  {icon} {url[:50]}... 速度:{result['speed_score']:.2f} 响应:{result['response_time']:.1f}s 总分:{result['total_score']:.2f}")
                    else:
                        print(f"  {icon} {url[:50]}... {result['status']}")
                        
                except Exception as e:
                    results[url] = {'total_score': 0, 'status': f'exception: {str(e)}'}
                    print(f"  ❌ {url[:50]}... 异常: {str(e)}")
        
        return results

    def remove_channel_suffix(self, channel_name):
        """去除频道名称的后缀"""
        if not channel_name:
            return channel_name
            
        suffixes = [
            '综合', '体育', '财经', '综艺', '电影', '电视剧', '新闻', '少儿', '音乐',
            '纪录', '科教', '戏曲', '军事', '农业', '国际', '高清', '超清', '4K',
            'HD', 'FHD', 'UHD', '标清', '普清'
        ]
        
        cleaned_name = channel_name
        for suffix in suffixes:
            pattern = r'\s*' + re.escape(suffix) + r'\s*$'
            cleaned_name = re.sub(pattern, '', cleaned_name)
            
        if cleaned_name != channel_name:
            print(f"🔧 去除后缀: '{channel_name}' -> '{cleaned_name}'")
            
        return cleaned_name.strip()

    def load_demo_structure(self):
        """加载模板频道结构"""
        print(f"正在读取模板频道: {self.demo_file}")
        demo_structure = {'categories': [], 'channels': {}}
        
        if not os.path.exists(self.demo_file):
            print(f"模板频道文件 {self.demo_file} 不存在，将创建示例文件")
            self.create_sample_demo_file()
            return demo_structure
            
        try:
            with open(self.demo_file, 'r', encoding='utf-8') as f:
                current_category = None
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.endswith(',#genre#'):
                        category = line.replace(',#genre#', '').strip()
                        current_category = category
                        if category not in demo_structure['categories']:
                            demo_structure['categories'].append(category)
                        if category not in demo_structure['channels']:
                            demo_structure['channels'][category] = []
                    elif current_category and ',' not in line and not line.endswith(',#genre#'):
                        channel_name = line.strip()
                        cleaned_name = self.remove_channel_suffix(channel_name)
                        if cleaned_name and cleaned_name not in demo_structure['channels'][current_category]:
                            demo_structure['channels'][current_category].append(cleaned_name)
                            
            print(f"模板频道加载完成: {len(demo_structure['categories'])} 个分类, "
                  f"共 {sum(len(channels) for channels in demo_structure['channels'].values())} 个频道")
            return demo_structure
            
        except Exception as e:
            print(f"读取模板频道文件时出错: {e}")
            return demo_structure

    def create_sample_demo_file(self):
        """创建示例模板频道文件"""
        sample_content = """央视频道,#genre#
CCTV-1
CCTV-2
CCTV-3
CCTV-4
CCTV-5
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
湖南卫视
浙江卫视
江苏卫视
北京卫视
东方卫视
广东卫视
深圳卫视
天津卫视
山东卫视
安徽卫视
重庆卫视
四川卫视
辽宁卫视
湖北卫视
河南卫视
黑龙江卫视
吉林卫视

地方频道,#genre#
北京文艺
北京科教
北京影视
北京财经
北京生活
北京青年
北京新闻
广东珠江
广东体育
广东公共
南方卫视
深圳都市
深圳公共
深圳电视剧

其他频道,#genre#
凤凰中文
凤凰资讯
星空卫视
华娱卫视
MTV中国
Channel V"""
        
        try:
            with open(self.demo_file, 'w', encoding='utf-8') as f:
                f.write(sample_content)
            print(f"已创建示例模板频道文件: {self.demo_file}")
        except Exception as e:
            print(f"创建模板频道示例文件失败: {e}")

    def load_alias_mapping(self):
        """加载别名映射"""
        print(f"正在读取别名文件: {self.alias_file}")
        alias_mapping = {}
        
        if not os.path.exists(self.alias_file):
            print(f"别名文件 {self.alias_file} 不存在，将创建示例文件")
            self.create_sample_alias_file()
            return alias_mapping
            
        try:
            with open(self.alias_file, 'r', encoding='utf-8') as f:
                current_standard = None
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if line.startswith('>'):
                        current_standard = line[1:].strip()
                        current_standard = self.remove_channel_suffix(current_standard)
                        alias_mapping[current_standard] = []
                    elif current_standard and line.startswith('-'):
                        alias_name = line[1:].strip()
                        alias_name = self.remove_channel_suffix(alias_name)
                        if alias_name and alias_name not in alias_mapping:
                            alias_mapping[alias_name] = current_standard
                            
            for standard_name in [k for k in alias_mapping.keys() if not any(k == v for v in alias_mapping.values())]:
                alias_mapping[standard_name] = standard_name
                
            print(f"别名映射加载完成: {len(alias_mapping)} 个别名规则")
            return alias_mapping
            
        except Exception as e:
            print(f"读取别名文件时出错: {e}")
            return {}

    def create_sample_alias_file(self):
        """创建示例别名文件"""
        sample_content = """# 别名映射文件
>CCTV-1
-CCTV1
-中央一套
-央视一套

>CCTV-2
-CCTV2
-中央二套
-央视二套

>湖南卫视
-湖南台
-芒果台
-湖南电视台"""
        
        try:
            with open(self.alias_file, 'w', encoding='utf-8') as f:
                f.write(sample_content)
            print(f"已创建示例别名文件: {self.alias_file}")
        except Exception as e:
            print(f"创建别名示例文件失败: {e}")

    def normalize_channel_name(self, channel_name):
        """标准化频道名称"""
        if not channel_name:
            return channel_name
        
        cleaned_name = self.remove_channel_suffix(channel_name)
            
        if cleaned_name in self.alias_mapping:
            standard_name = self.alias_mapping[cleaned_name]
            if standard_name != cleaned_name:
                print(f"🔤 别名映射: '{cleaned_name}' -> '{standard_name}'")
            return standard_name
        
        for alias, standard in self.alias_mapping.items():
            if alias in cleaned_name and alias != cleaned_name:
                print(f"🔤 模糊映射: '{cleaned_name}' -> '{standard}'")
                return standard
        
        return cleaned_name

    def load_blacklist(self):
        """加载黑名单"""
        print(f"正在读取黑名单: {self.blacklist_file}")
        blacklist = {'keywords': [], 'domains': [], 'ips': []}
        
        if not os.path.exists(self.blacklist_file):
            print(f"黑名单文件 {self.blacklist_file} 不存在，将创建示例文件")
            self.create_sample_blacklist_file()
            return blacklist
            
        try:
            with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?$'
                    if re.match(ip_pattern, line):
                        blacklist['ips'].append(line)
                    elif re.match(r'^[a-zA-Z0-9.-]+(?::\d+)?$', line) and '.' in line:
                        blacklist['domains'].append(line)
                    else:
                        blacklist['keywords'].append(line)
                        
            print(f"黑名单加载完成: 关键字({len(blacklist['keywords'])}), "
                  f"域名({len(blacklist['domains'])}), IP({len(blacklist['ips'])})")
            return blacklist
            
        except Exception as e:
            print(f"读取黑名单文件时出错: {e}")
            return blacklist

    def create_sample_blacklist_file(self):
        """创建示例黑名单文件"""
        sample_content = """# 黑名单文件
测试频道
付费
成人
赌博
bad-domain.com
192.168.1.100"""
        
        try:
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                f.write(sample_content)
            print(f"已创建示例黑名单文件: {self.blacklist_file}")
        except Exception as e:
            print(f"创建黑名单示例文件失败: {e}")

    def is_blacklisted(self, program_name, stream_url):
        """检查频道是否在黑名单中"""
        if not self.config['blacklist_enabled']:
            return False, None
            
        for keyword in self.blacklist['keywords']:
            if keyword and keyword in program_name:
                return True, f"频道名称包含黑名单关键字: {keyword}"
        
        try:
            parsed_url = urlparse(stream_url)
            hostname = parsed_url.hostname
            port = parsed_url.port
            
            if not hostname:
                return False, None
            
            for black_ip in self.blacklist['ips']:
                if ':' in black_ip:
                    ip, black_port = black_ip.split(':')
                    black_port = int(black_port)
                    if hostname == ip and port == black_port:
                        return True, f"IP地址在黑名单中: {black_ip}"
                else:
                    if hostname == black_ip:
                        return True, f"IP地址在黑名单中: {black_ip}"
            
            for domain in self.blacklist['domains']:
                if ':' in domain:
                    domain_name, domain_port = domain.split(':')
                    domain_port = int(domain_port)
                    if hostname == domain_name and port == domain_port:
                        return True, f"域名在黑名单中: {domain}"
                else:
                    if hostname == domain:
                        return True, f"域名在黑名单中: {domain}"
                    if hostname.endswith('.' + domain):
                        return True, f"子域名在黑名单中: {domain}"
                        
        except Exception as e:
            print(f"解析URL时出错: {stream_url}, 错误: {e}")
            
        return False, None

    def fetch_streams_from_url(self, url):
        """抓取单个源的流数据"""
        print(f"正在爬取: {url}")
        try:
            response = self.session.get(url, timeout=15)
            response.encoding = 'utf-8'
            if response.status_code == 200:
                return response.text
            else:
                print(f"获取失败，状态码: {response.status_code}")
        except Exception as e:
            print(f"请求错误: {e}")
        return None

    def load_local_streams(self):
        """加载本地源文件"""
        if not self.config['local_sources_enabled']:
            return []
            
        print(f"正在读取本地源: {self.local_file}")
        local_streams = []
        
        if not os.path.exists(self.local_file):
            print(f"本地源文件 {self.local_file} 不存在，将创建示例文件")
            self.create_sample_local_file()
            return []
            
        try:
            with open(self.local_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            current_genre = None
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                    
                if line.endswith(',#genre#'):
                    current_genre = line.replace(',#genre#', '').strip()
                    continue
                    
                if ',' in line and not line.endswith(',#genre#'):
                    parts = line.split(',', 1)
                    if len(parts) == 2 and parts[1].startswith(('http://', 'https://')):
                        program_name = parts[0].strip()
                        stream_url = parts[1].strip()
                        
                        normalized_name = self.normalize_channel_name(program_name)
                        
                        is_blocked, reason = self.is_blacklisted(normalized_name, stream_url)
                        if is_blocked:
                            print(f"🚫 拦截本地源: {normalized_name} - {reason}")
                            continue
                        
                        if current_genre:
                            normalized_name = f"{current_genre} - {normalized_name}"
                            
                        local_streams.append({
                            "program_name": normalized_name,
                            "stream_url": stream_url,
                            "logo": None,
                            "source": "local"
                        })
                        
            print(f"从本地源读取到 {len(local_streams)} 个频道")
            return local_streams
            
        except Exception as e:
            print(f"读取本地源文件时出错: {e}")
            return []

    def create_sample_local_file(self):
        """创建示例本地源文件"""
        sample_content = """央视频道,#genre#
CCTV-1,http://example.com/cctv1
CCTV-2,http://example.com/cctv2
CCTV-5,http://example.com/cctv5

卫视频道,#genre#
湖南卫视,http://example.com/hunan
浙江卫视,http://example.com/zhejiang
江苏卫视,http://example.com/jiangsu"""
        
        try:
            with open(self.local_file, 'w', encoding='utf-8') as f:
                f.write(sample_content)
            print(f"已创建示例本地源文件: {self.local_file}")
        except Exception as e:
            print(f"创建示例文件失败: {e}")

    def fetch_all_streams(self):
        """抓取所有源的流数据"""
        all_streams = []
        successful_sources = 0
        
        # 加载本地源
        if self.config['local_sources_enabled']:
            local_content = self.load_local_streams()
            if local_content:
                local_text = []
                for stream in local_content:
                    local_text.append(f"{stream['program_name']},{stream['stream_url']}")
                all_streams.append("\n".join(local_text))
                successful_sources += 1
                print("✓ 本地源加载成功")
        
        # 抓取网络源
        if self.config['network_sources_enabled']:
            for url in self.urls:
                if content := self.fetch_streams_from_url(url):
                    all_streams.append(content)
                    successful_sources += 1
                else:
                    print(f"跳过来源: {url}")
                time.sleep(1)
            
        print(f"成功获取 {successful_sources} 个源")
        return "\n".join(all_streams) if all_streams else None

    def parse_m3u(self, content):
        """解析M3U格式"""
        streams = []
        current_program = None
        current_logo = None
        
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF"):
                if match := re.search(r'tvg-name="([^"]+)"', line):
                    current_program = match.group(1).strip()
                elif not current_program:
                    if match := re.search(r'#EXTINF:.*?,(.+)', line):
                        current_program = match.group(1).strip()
                
                if match := re.search(r'tvg-logo="([^"]+)"', line):
                    current_logo = match.group(1).strip()
                    
            elif line.startswith(('http://', 'https://')):
                if current_program:
                    normalized_name = self.normalize_channel_name(current_program)
                    
                    is_blocked, reason = self.is_blacklisted(normalized_name, line)
                    if is_blocked:
                        print(f"🚫 拦截频道: {normalized_name} - {reason}")
                        current_program = None
                        current_logo = None
                        continue
                    
                    streams.append({
                        "program_name": normalized_name,
                        "stream_url": line,
                        "logo": current_logo
                    })
                    current_program = None
                    current_logo = None
                    
        return streams

    def parse_txt(self, content):
        """解析TXT格式"""
        streams = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            separators = [',', ', ', ' ,', '#', 'http']
            for sep in separators:
                if sep in line and line.startswith(sep) is False:
                    parts = line.split(sep, 1)
                    if len(parts) == 2 and parts[1].startswith(('http://', 'https://')):
                        program_name = parts[0].strip()
                        stream_url = parts[1].strip()
                        
                        normalized_name = self.normalize_channel_name(program_name)
                        
                        is_blocked, reason = self.is_blacklisted(normalized_name, stream_url)
                        if is_blocked:
                            print(f"🚫 拦截频道: {normalized_name} - {reason}")
                            continue
                            
                        streams.append({
                            "program_name": normalized_name,
                            "stream_url": stream_url,
                            "logo": None
                        })
                        break
        return streams

    def organize_streams(self, content):
        """整理和去重流数据"""
        if content.startswith("#EXTM3U"):
            streams = self.parse_m3u(content)
        else:
            streams = self.parse_txt(content)
            
        local_streams = self.load_local_streams()
        all_streams = streams + local_streams
        
        if not all_streams:
            print("未解析到有效的流数据")
            return pd.DataFrame()
            
        df = pd.DataFrame(all_streams)
        print(f"解析到 {len(df)} 个流 (网络源: {len(streams)}, 本地源: {len(local_streams)})")
        
        initial_count = len(df)
        df = df.drop_duplicates(subset=['program_name', 'stream_url'])
        print(f"去重后剩余 {len(df)} 个流 (移除 {initial_count - len(df)} 个重复项)")
        
        return df.groupby('program_name')['stream_url'].apply(list).reset_index()

    def build_channel_mapping(self, grouped_streams):
        """构建频道映射，进行FFmpeg测速并排序"""
        channel_mapping = {}
        
        # 收集所有模板频道
        template_channels = set()
        for category_channels in self.demo_structure['channels'].values():
            template_channels.update(category_channels)
        
        # 构建初始频道映射
        for _, row in grouped_streams.iterrows():
            actual_channel = row['program_name']
            urls = row['stream_url']
            
            cleaned_actual = self.remove_channel_suffix(actual_channel)
            
            matched_template_channel = None
            for template_channel in template_channels:
                if (template_channel == cleaned_actual or 
                    template_channel in cleaned_actual or
                    cleaned_actual in template_channel):
                    matched_template_channel = template_channel
                    break
            
            if matched_template_channel:
                if matched_template_channel not in channel_mapping:
                    channel_mapping[matched_template_channel] = []
                channel_mapping[matched_template_channel].extend(urls)
        
        # 对每个频道的源进行FFmpeg测速和排序
        print("🎯 开始FFmpeg测速优化...")
        optimized_mapping = {}
        
        for channel, urls in channel_mapping.items():
            print(f"\n📊 测试频道: {channel} ({len(urls)}个源)")
            
            # 批量测试所有源
            test_results = self.test_streams_batch(urls)
            
            # 根据测速结果排序
            sorted_urls = sorted(urls, key=lambda url: test_results.get(url, {}).get('total_score', 0), reverse=True)
            
            # 限制每个频道的源数量
            limited_urls = sorted_urls[:self.config['max_urls_per_channel']]
            optimized_mapping[channel] = limited_urls
            
            # 显示优化结果
            if limited_urls:
                best_score = test_results.get(limited_urls[0], {}).get('total_score', 0)
                print(f"  ✅ 优化完成: 保留{len(limited_urls)}个源，最佳得分: {best_score:.2f}")
            else:
                print(f"  ⚠️  无可用源")
        
        return optimized_mapping

    def save_to_txt(self, channel_mapping, filename="iptv.txt"):
        """保存为TXT格式"""
        if not channel_mapping or not self.config['save_txt_enabled']:
            return
            
        output_lines = []
        total_channels = 0
        total_urls = 0
        
        for category in self.demo_structure['categories']:
            if category not in self.demo_structure['channels']:
                continue
                
            output_lines.append(f"{category},#genre#")
            category_channels = 0
            category_urls = 0
            
            for template_channel in self.demo_structure['channels'][category]:
                if template_channel in channel_mapping:
                    urls = channel_mapping[template_channel]
                    for url in urls:
                        output_lines.append(f"{template_channel},{url}")
                    category_channels += 1
                    category_urls += len(urls)
            
            total_channels += category_channels
            total_urls += category_urls
            output_lines.append("")
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines).strip())
                
        print(f"📄 TXT文件已保存: {os.path.abspath(filename)}")
        print(f"📊 最终统计: {total_channels} 个频道, {total_urls} 个源")

    def save_to_m3u(self, channel_mapping, filename="iptv.m3u"):
        """保存为M3U格式"""
        if not channel_mapping or not self.config['save_m3u_enabled']:
            return
            
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            
            for category in self.demo_structure['categories']:
                if category not in self.demo_structure['channels']:
                    continue
                    
                for template_channel in self.demo_structure['channels'][category]:
                    if template_channel in channel_mapping:
                        urls = channel_mapping[template_channel]
                        for url in urls:
                            f.write(f'#EXTINF:-1 tvg-name="{template_channel}",{template_channel}\n{url}\n')
                    
        print(f"📄 M3U文件已保存: {os.path.abspath(filename)}")

    def run(self):
        """运行爬虫"""
        print("🎬 开始抓取IPTV直播源...")
        
        if content := self.fetch_all_streams():
            print("🔄 整理数据中...")
            organized = self.organize_streams(content)
            
            if not organized.empty:
                print("⚡ 构建频道映射...")
                channel_mapping = self.build_channel_mapping(organized)
                
                if channel_mapping:
                    self.save_to_txt(channel_mapping)
                    self.save_to_m3u(channel_mapping)
                    print("🎉 处理完成!")
                else:
                    print("❌ 没有匹配模板的频道数据")
            else:
                print("❌ 没有有效的流数据可处理")
        else:
            print("❌ 未能获取有效数据")

if __name__ == "__main__":
    crawler = IPTVCrawler()
    crawler.run()
