import requests
import pandas as pd
import re
import os
import time
import concurrent.futures
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse

class IPTV:
    """IPTV直播源抓取与测速工具"""
    
    def __init__(self, timeout=8, max_workers=10, test_size_kb=64):
        """
        初始化工具
        
        Args:
            timeout: 请求超时时间（秒）
            max_workers: 最大并发线程数
            test_size_kb: 测速数据大小（KB）
        """
        # 配置参数
        self.timeout = timeout
        self.max_workers = max_workers
        self.test_size = test_size_kb * 1024
        
        # 请求会话配置
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        })
        
        # 数据源配置 - 更多直播源
        self.source_urls = [
            "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
            "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
            "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",  
            "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
            "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
            "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
            "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
            "http://47.120.41.246:8899/zb.txt",
        ]
        
        # 正则表达式预编译
        self.ipv4_pattern = re.compile(r'^http://(\d{1,3}\.){3}\d{1,3}')
        self.ipv6_pattern = re.compile(r'^http://\[([a-fA-F0-9:]+)\]')
        self.channel_pattern = re.compile(r'^([^,#]+)')
        self.extinf_pattern = re.compile(r'#EXTINF:.*?,(.+)')
        
        # 文件路径配置
        self.template_file = os.path.join(os.path.dirname(__file__), "demo.txt")
        self.output_files = {
            'txt': os.path.join(os.path.dirname(__file__), "iptv.txt"),
            'm3u': os.path.join(os.path.dirname(__file__), "iptv.m3u"),
        }
        
        # 初始化状态
        self.template_channels = self.load_template_channels()
        self.all_streams = []

    def load_template_channels(self) -> Set[str]:
        """加载模板文件中的频道列表"""
        channels = set()
        if not os.path.exists(self.template_file):
            print(f"⚠️ 模板文件 {self.template_file} 不存在，将处理所有频道")
            return channels
        
        try:
            with open(self.template_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if match := self.channel_pattern.match(line):
                            channels.add(match.group(1).strip())
            print(f"加载模板频道 {len(channels)} 个")
        except Exception as e:
            print(f"加载模板文件错误: {str(e)}")
        
        return channels

    # ==================== 数据获取与处理 ====================
    
    def fetch_streams(self) -> Optional[str]:
        """从所有源URL抓取直播源"""
        contents = []
        successful_sources = 0
        
        for url in self.source_urls:
            print(f"抓取源: {self._extract_domain(url)}")
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                
                # 验证内容有效性
                if self.validate_content(response.text):
                    contents.append(response.text)
                    successful_sources += 1
                    print(f"  ✓ 成功")
                else:
                    print(f"  ⚠️ 内容无效")
                    
            except Exception as e:
                print(f"  ✗ 失败: {str(e)}")
        
        print(f"成功抓取 {successful_sources}/{len(self.source_urls)} 个源")
        return "\n".join(contents) if contents else None

    def validate_content(self, content: str) -> bool:
        """验证内容是否为有效的直播源格式"""
        lines = content.splitlines()
        valid_lines = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('http') or (',' in line and 'http' in line):
                valid_lines += 1
        
        return valid_lines >= 5

    def parse_content(self, content: str) -> pd.DataFrame:
        """解析直播源内容"""
        streams = []
        
        # 自动检测格式并解析
        if content.startswith("#EXTM3U"):
            streams.extend(self.parse_m3u_content(content))
        else:
            streams.extend(self.parse_txt_content(content))
        
        if not streams:
            print("未解析到有效直播源")
            return pd.DataFrame(columns=['program_name', 'stream_url'])
        
        df = pd.DataFrame(streams)
        
        # 数据清洗
        df = self.clean_stream_data(df)
        
        print(f"解析到 {len(df)} 个直播源，{len(df['program_name'].unique())} 个频道")
        return df

    def parse_m3u_content(self, content: str) -> List[Dict]:
        """解析M3U格式内容"""
        streams = []
        current_program = None
        
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF"):
                # 尝试多种格式提取节目名
                if match := re.search(r'tvg-name="([^"]+)"', line):
                    current_program = match.group(1).strip()
                elif match := self.extinf_pattern.search(line):
                    current_program = match.group(1).strip()
            elif line.startswith("http"):
                if current_program:
                    streams.append({
                        "program_name": current_program,
                        "stream_url": line
                    })
                current_program = None
        
        return streams

    def parse_txt_content(self, content: str) -> List[Dict]:
        """解析TXT格式内容"""
        streams = []
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            # 支持多种分隔符
            if ',' in line:
                parts = line.split(',', 1)
            elif ' ' in line and 'http' in line:
                parts = line.split(' ', 1)
            else:
                continue
                
            if len(parts) == 2:
                program_name = parts[0].strip()
                stream_url = parts[1].strip()
                
                if program_name and stream_url.startswith('http'):
                    streams.append({
                        "program_name": program_name,
                        "stream_url": stream_url
                    })
        
        return streams

    def clean_stream_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """数据清洗"""
        if df.empty:
            return df
        
        # 去除节目名中的多余空格
        df['program_name'] = df['program_name'].str.strip()
        
        # 过滤无效URL
        initial_count = len(df)
        df = df[df['stream_url'].str.startswith('http')]
        
        # 去除明显无效的节目名
        invalid_names = ['', 'None', 'null', 'undefined']
        df = df[~df['program_name'].isin(invalid_names)]
        
        print(f"数据清洗: {initial_count} -> {len(df)} 个源")
        return df

    def organize_streams(self, df: pd.DataFrame) -> pd.DataFrame:
        """整理直播源数据，每个频道最多保留30个源用于测速"""
        grouped = df.groupby('program_name')['stream_url'].apply(list).reset_index()
        
        # 限制每个频道的源数量为30个
        grouped['stream_url'] = grouped['stream_url'].apply(lambda x: x[:30])
        
        print(f"整理后: {len(grouped)} 个频道，每个频道最多30个源")
        return grouped

    # ==================== 增强测速功能 ====================
    
    def test_single_url(self, url: str) -> Tuple[Optional[float], Optional[str], float]:
        """测试单个URL的速度，返回速度、错误信息和响应时间"""
        start_time = time.time()
        
        try:
            response = self.session.get(
                url, 
                timeout=self.timeout, 
                stream=True,
                headers={'Range': f'bytes=0-{self.test_size-1}'}
            )
            response_time = time.time() - start_time
            
            if response.status_code not in [200, 206]:
                return None, f"HTTP {response.status_code}", response_time
            
            content_length = 0
            chunk_start_time = time.time()
            
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    break
                    
                content_length += len(chunk)
                if content_length >= self.test_size:
                    break
                    
                # 检查下载是否超时
                if time.time() - chunk_start_time > self.timeout:
                    return None, "下载超时", response_time
            
            if content_length == 0:
                return 0, "无数据", response_time
            
            total_time = time.time() - start_time
            speed = content_length / total_time / 1024  # KB/s
            
            return speed, None, response_time
            
        except requests.exceptions.Timeout:
            return None, "请求超时", time.time() - start_time
        except requests.exceptions.SSLError:
            return None, "SSL错误", time.time() - start_time
        except requests.exceptions.ConnectionError:
            return None, "连接失败", time.time() - start_time
        except requests.exceptions.HTTPError as e:
            return None, f"HTTP错误 {e.response.status_code}", time.time() - start_time
        except Exception as e:
            return None, f"错误: {str(e)}", time.time() - start_time

    def test_urls_concurrently(self, urls: List[str]) -> List[Tuple[str, Optional[float], Optional[str], float]]:
        """并发测试URL列表"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {executor.submit(self.test_single_url, url): url for url in urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                speed, error, response_time = future.result()
                results.append((url, speed, error, response_time))
        return results

    def test_all_channels(self, grouped_streams: pd.DataFrame) -> Dict[str, List[Tuple[str, float]]]:
        """测试所有频道并保留最佳8个源"""
        results = {}
        total_channels = len(grouped_streams)
        tested_channels = 0
        successful_channels = 0
        
        print(f"\n开始测速 {total_channels} 个频道")
        print("每个频道测试最多30个源，保留最优8个")
        
        for idx, (_, row) in enumerate(grouped_streams.iterrows(), 1):
            channel = row['program_name']
            urls = row['stream_url']
            
            print(f"[{idx}/{total_channels}] 测试频道: {channel} ({len(urls)}个源)")
            
            test_results = self.test_urls_concurrently(urls)
            valid_streams = []
            
            fast_count = 0
            medium_count = 0
            slow_count = 0
            failed_count = 0
            
            for url, speed, error, response_time in test_results:
                if speed is not None:
                    valid_streams.append((url, speed))
                    if speed > 500:
                        fast_count += 1
                    elif speed > 100:
                        medium_count += 1
                    else:
                        slow_count += 1
                else:
                    failed_count += 1
            
            # 按速度排序并保留最佳8个
            valid_streams.sort(key=lambda x: x[1], reverse=True)
            best_streams = valid_streams[:8]
            results[channel] = best_streams
            
            tested_channels += 1
            if best_streams:
                successful_channels += 1
                best_speed = best_streams[0][1]
                print(f"  ✅ 成功: 最佳速度 {best_speed:.1f} KB/s")
                print(f"     详情: 快速{fast_count} 中速{medium_count} 慢速{slow_count} 失败{failed_count}")
                print(f"     保留: {len(best_streams)}个最优源")
            else:
                print(f"  ❌ 失败: 无有效源")
        
        print(f"\n测速完成: {successful_channels}/{tested_channels} 个频道有有效源")
        return results

    # ==================== 模板匹配和结果生成 ====================
    
    def filter_by_template(self, speed_results: Dict[str, List[Tuple[str, float]]]) -> Dict[str, List[Tuple[str, float]]]:
        """根据模板频道过滤结果"""
        if not self.template_channels:
            print("未使用模板过滤，保留所有频道")
            return speed_results
        
        filtered_results = {}
        matched_count = 0
        
        for channel in self.template_channels:
            if channel in speed_results and speed_results[channel]:
                filtered_results[channel] = speed_results[channel]
                matched_count += 1
        
        print(f"模板匹配: {matched_count}/{len(self.template_channels)} 个频道")
        
        # 显示未匹配的模板频道
        unmatched = self.template_channels - set(speed_results.keys())
        if unmatched:
            print(f"未找到源的模板频道: {len(unmatched)}个")
            for channel in list(unmatched)[:10]:  # 只显示前10个
                print(f"  - {channel}")
            if len(unmatched) > 10:
                print(f"  ... 还有 {len(unmatched) - 10} 个")
        
        return filtered_results

    def generate_output_files(self, speed_results: Dict[str, List[Tuple[str, float]]]):
        """生成所有输出文件"""
        self.generate_txt_file(speed_results)
        self.generate_m3u_file(speed_results)
        self.generate_report(speed_results)

    def generate_txt_file(self, results: Dict[str, List[Tuple[str, float]]]):
        """生成TXT格式文件"""
        categories = {
            "央视频道,#genre#": ["CCTV", "央视"],
            "卫视频道,#genre#": ["卫视", "湖南", "浙江", "江苏", "东方", "北京"],
            "地方频道,#genre#": ["重庆", "广东", "深圳", "南方", "天津", "河北"],
            "港澳频道,#genre#": ["凤凰", "翡翠", "明珠", "澳亚"],
            "其他频道,#genre#": []
        }
        
        categorized = {cat: [] for cat in categories}
        
        for channel in self.get_ordered_channels(results.keys()):
            streams = results.get(channel, [])
            if not streams:
                continue
                
            matched = False
            for cat, keywords in categories.items():
                if any(keyword in channel for keyword in keywords):
                    categorized[cat].extend(
                        f"{channel},{url} # 速度: {speed:.1f}KB/s" 
                        for url, speed in streams
                    )
                    matched = True
                    break
            
            if not matched:
                categorized["其他频道,#genre#"].extend(
                    f"{channel},{url} # 速度: {speed:.1f}KB/s" 
                    for url, speed in streams
                )
        
        with open(self.output_files['txt'], 'w', encoding='utf-8') as f:
            for cat, items in categorized.items():
                if items:
                    f.write(f"\n{cat}\n")
                    f.write("\n".join(items) + "\n")
        
        print(f"生成TXT文件: {self.output_files['txt']}")

    def generate_m3u_file(self, results: Dict[str, List[Tuple[str, float]]]):
        """生成M3U格式文件"""
        with open(self.output_files['m3u'], 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            
            for channel in self.get_ordered_channels(results.keys()):
                streams = results.get(channel, [])
                for url, speed in streams:
                    quality = self.get_speed_quality(speed)
                    f.write(f'#EXTINF:-1 tvg-name="{channel}",{channel} [速度: {speed:.1f}KB/s {quality}]\n{url}\n')
        
        print(f"生成M3U文件: {self.output_files['m3u']}")

    def generate_report(self, results: Dict[str, List[Tuple[str, float]]]):
        """生成测速报告"""
        speed_stats = []
        valid_channels = []
        total_sources = 0
        
        for channel, streams in results.items():
            if streams:
                best_speed = streams[0][1]
                speed_stats.append(best_speed)
                valid_channels.append((channel, best_speed, len(streams)))
                total_sources += len(streams)
        
        if not speed_stats:
            print("⚠️ 无有效测速结果")
            return
        
        # 按速度排序频道
        valid_channels.sort(key=lambda x: x[1], reverse=True)
        
        print("\n" + "="*50)
        print("测速报告")
        print("="*50)
        print(f"有效频道数: {len(valid_channels)}")
        print(f"总源数量: {total_sources}")
        print(f"平均速度: {sum(speed_stats)/len(speed_stats):.1f} KB/s")
        print(f"最快速度: {max(speed_stats):.1f} KB/s")
        print(f"最慢速度: {min(speed_stats):.1f} KB/s")
        
        print("\n频道速度排名 TOP 20:")
        for i, (channel, speed, count) in enumerate(valid_channels[:20], 1):
            print(f"{i:2d}. {channel}: {speed:.1f} KB/s ({count}个源)")

    # ==================== 辅助方法 ====================
    
    def get_ordered_channels(self, channels: List[str]) -> List[str]:
        """按照模板顺序排序频道列表"""
        if not self.template_channels:
            return sorted(channels)
        
        ordered = []
        # 首先按模板顺序
        with open(self.template_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if match := self.channel_pattern.match(line):
                        channel = match.group(1).strip()
                        if channel in channels and channel not in ordered:
                            ordered.append(channel)
        
        # 添加未在模板中的频道（理论上不应该有，因为已经过滤了）
        for channel in channels:
            if channel not in ordered:
                ordered.append(channel)
                
        return ordered

    def _extract_domain(self, url: str) -> str:
        """从URL提取域名"""
        try:
            netloc = urlparse(url).netloc
            return netloc.split(':')[0]
        except:
            return url[:30] + "..." if len(url) > 30 else url

    def get_speed_quality(self, speed: float) -> str:
        """获取速度质量评级"""
        if speed > 1000: return "极佳"
        if speed > 500: return "优秀"
        if speed > 200: return "良好"
        if speed > 100: return "一般"
        if speed > 50: return "较差"
        return "极差"

    # ==================== 主流程 ====================
    
    def run(self):
        """运行主流程"""
        print("="*50)
        print("IPTV直播源处理工具")
        print("="*50)
        
        start_time = time.time()
        
        try:
            # 第一步：抓取所有直播源
            print("\n第一步：抓取直播源...")
            content = self.fetch_streams()
            if not content:
                print("❌ 未能获取有效数据")
                return
            
            # 第二步：解析和整理数据
            print("\n第二步：解析直播源数据...")
            df = self.parse_content(content)
            if df.empty:
                print("❌ 未解析到有效直播源")
                return
            
            # 第三步：整理数据，每个频道最多30个源
            grouped = self.organize_streams(df)
            
            # 第四步：对所有频道进行测速
            print("\n第三步：测速优化...")
            speed_results = self.test_all_channels(grouped)
            
            # 第五步：根据模板频道过滤结果
            print("\n第四步：模板匹配...")
            filtered_results = self.filter_by_template(speed_results)
            
            # 第六步：生成输出文件
            print("\n第五步：生成输出文件...")
            self.generate_output_files(filtered_results)
            
            # 完成统计
            total_time = time.time() - start_time
            print(f"\n🎉 处理完成! 总耗时: {total_time:.1f}秒")
            
        except Exception as e:
            print(f"❌ 处理过程中发生错误: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    # 配置参数
    config = {
        'timeout': 6,      # 请求超时时间(秒)
        'max_workers': 8,  # 最大并发数（提高并发）
        'test_size_kb': 32 # 测速数据大小(KB)
    }
    
    tool = IPTV(**config)
    tool.run()
