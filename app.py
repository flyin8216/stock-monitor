import streamlit as st
import akshare as ak
import tushare as ts
import pandas as pd
import json
import os
from datetime import datetime
from typing import Dict, Optional, List

# ================================
# 配置常量
# ================================
class Config:
    """应用配置"""
    DATA_FILE = "stock_strategy_data.json"
    
    # Tushare Token - 优先从环境变量读取，保护隐私
    # 本地开发时可以在这里填写，部署时使用 Streamlit Secrets
    TUSHARE_TOKEN = os.environ.get(
        "TUSHARE_TOKEN",
        st.secrets.get("TUSHARE_TOKEN", "") if hasattr(st, 'secrets') and "TUSHARE_TOKEN" in st.secrets else ""
    )
    
    CACHE_TTL = 600  # 缓存10分钟
    LOOKBACK_YEARS = 5  # 数据回溯年限
    

    
    # 指数分组配置
    INDEX_GROUPS = {
        "🏛 核心宽基": {
            "上证指数": "sh000001", 
            "创业板指": "sz399006", 
            "沪深300": "sh000300", 
            "中证500": "sh000905", 
            "上证50": "sh000016", 
            "中证1000": "sh000852"
        },
        "💊 行业板块": {
            "中证红利": "sh000922", 
            "中证医疗": "sz399989", 
            "全指医药": "sh000991", 
            "全指消费": "sh000990",
            "中证消费": "sh000932",
            "全指信息": "sh000993", 
            "中证传媒": "sz399971", 
            "食品饮料": "sz399396",
            "中证军工": "sz399967",
            "中概互联": "H30533"
        },
        "🌍 全球市场": {
            "恒生指数": "hkHSI", 
            "恒生科技": "hkHSTECH", 
            "恒生医疗": "hkHSHCI", 
            "标普500": "gb.INX", 
            "纳指100": "gb.NDX"
        }
    }

# ================================
# 数据持久化
# ================================
class DataManager:
    """数据存储管理器"""
    
    @staticmethod
    def get_all_index_names() -> List[str]:
        """获取所有指数名称"""
        names = []
        for group in Config.INDEX_GROUPS.values():
            names.extend(group.keys())
        return names
    
    @staticmethod
    def load() -> Dict:
        """加载数据"""
        all_names = DataManager.get_all_index_names()
        default_data = {
            "supports": {name: 3000 for name in all_names},
            "atmospheres": {name: 4000 for name in all_names},
            "notes": {name: [] for name in all_names}
        }
        
        if os.path.exists(Config.DATA_FILE):
            try:
                with open(Config.DATA_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    for key in default_data:
                        if key in saved:
                            default_data[key].update(saved[key])
            except Exception as e:
                st.warning(f"数据加载失败: {e}")
        
        return default_data
    
    @staticmethod
    def save(data: Dict):
        """保存数据"""
        try:
            with open(Config.DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            st.error(f"数据保存失败: {e}")

# ================================
# Tushare 集成
# ================================
class TushareClient:
    """Tushare API 客户端"""
    _instance = None
    
    @classmethod
    def get_instance(cls) -> Optional[ts.pro_api]:
        """获取Tushare客户端单例"""
        if cls._instance is None and Config.TUSHARE_TOKEN:
            try:
                ts.set_token(Config.TUSHARE_TOKEN)
                cls._instance = ts.pro_api()
            except Exception as e:
                print(f"Tushare初始化失败: {e}")
        return cls._instance

# ================================
# 数据获取引擎
# ================================
class DataFetcher:
    """统一的数据获取接口"""
    
    @staticmethod
    def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """通用数据清洗"""
        # 统一列名为小写
        df.columns = [c.lower() for c in df.columns]
        
        # 标准化日期列名
        date_col = next((c for c in df.columns if c in ['date', 'time', '日期']), None)
        if date_col:
            df.rename(columns={date_col: 'date'}, inplace=True)
        
        # 转换日期格式
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df.dropna(subset=['date'], inplace=True)
        
        # 过滤时间范围
        cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=Config.LOOKBACK_YEARS)
        df = df[df['date'] >= cutoff_date]
        
        # 确保必需的列存在并转换数值类型
        for col in ['close', 'high', 'low']:
            if col not in df.columns:
                df[col] = df['close']
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=['close'], inplace=True)
        return df
    
    @staticmethod
    def _extract_metrics(df: pd.DataFrame) -> Optional[Dict]:
        """从DataFrame提取关键指标"""
        if df.empty:
            return None
        
        current_value = float(df.iloc[-1]['close'])
        high_idx = df['high'].idxmax()
        low_idx = df['low'].idxmin()
        
        return {
            "cur": current_value,
            "hv": float(df.loc[high_idx, 'high']),
            "hd": df.loc[high_idx, 'date'].strftime('%Y-%m-%d'),
            "lv": float(df.loc[low_idx, 'low']),
            "ld": df.loc[low_idx, 'date'].strftime('%Y-%m-%d')
        }
    
    @staticmethod
    def fetch_zhonggai_tushare(pro: ts.pro_api) -> Optional[Dict]:
        """通过Tushare获取中概互联数据"""
        try:
            end_date = pd.Timestamp.now().strftime('%Y%m%d')
            start_date = (pd.Timestamp.now() - pd.DateOffset(years=Config.LOOKBACK_YEARS)).strftime('%Y%m%d')
            
            df = pro.index_daily(ts_code='H30533.CSI', start_date=start_date, end_date=end_date)
            
            if df.empty:
                return None
            
            df = df.sort_values('trade_date')
            df.rename(columns={
                'trade_date': 'date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close'
            }, inplace=True)
            
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
            
            for col in ['close', 'high', 'low']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df.dropna(subset=['close'], inplace=True)
            
            if df.empty:
                return None
            
            metrics = DataFetcher._extract_metrics(df)
            if metrics:
                metrics["source"] = "Tushare"
            return metrics
            
        except Exception as e:
            print(f"Tushare获取中概互联失败: {e}")
            return None
    
    @staticmethod
    def fetch_zhonggai_etf() -> Optional[Dict]:
        """通过ETF获取中概互联数据（已废弃 - 保留作为备用）"""
        try:
            df = ak.fund_etf_hist_em(
                symbol="513050", 
                period="daily", 
                start_date="20190101", 
                end_date="20261231", 
                adjust="qfq"
            )
            
            if df.empty:
                return None
            
            # 清洗列名
            df.columns = [str(c).strip() for c in df.columns]
            rename_map = {
                '日期': 'date', 
                '开盘': 'open', 
                '收盘': 'close', 
                '最高': 'high', 
                '最低': 'low'
            }
            df.rename(columns=rename_map, inplace=True)
            
            df = DataFetcher._clean_dataframe(df)
            
            if df.empty:
                return None
            
            # 注意：ETF数据不再进行转换，直接使用原始值
            metrics = DataFetcher._extract_metrics(df)
            if metrics:
                metrics["source"] = "ETF"
            
            return metrics
            
        except Exception as e:
            print(f"ETF数据获取失败: {e}")
            return None
    
    @staticmethod
    def fetch_hongkong_index(code: str) -> Optional[Dict]:
        """获取港股指数数据"""
        try:
            hk_code = code.replace("hk", "")
            df = ak.stock_hk_index_daily_em(symbol=hk_code)
            
            if df.empty:
                return None
            
            df.columns = [c.lower().strip() for c in df.columns]
            if 'time' in df.columns:
                df.rename(columns={'time': 'date'}, inplace=True)
            if 'latest' in df.columns:
                df.rename(columns={'latest': 'close'}, inplace=True)
            
            df = DataFetcher._clean_dataframe(df)
            return DataFetcher._extract_metrics(df)
            
        except Exception as e:
            print(f"港股指数获取失败 ({code}): {e}")
            return None
    
    @staticmethod
    def fetch_us_index(code: str) -> Optional[Dict]:
        """获取美股指数数据"""
        try:
            symbol = code.replace("gb.", "")
            if symbol == "INX":
                symbol = ".INX"
            elif symbol == "NDX":
                symbol = ".NDX"
            
            df = ak.index_us_stock_sina(symbol=symbol)
            df = DataFetcher._clean_dataframe(df)
            return DataFetcher._extract_metrics(df)
            
        except Exception as e:
            print(f"美股指数获取失败 ({code}): {e}")
            return None
    
    @staticmethod
    def fetch_a_share_index(code: str) -> Optional[Dict]:
        """获取A股指数数据"""
        try:
            df = ak.stock_zh_index_daily_em(symbol=code)
            df = DataFetcher._clean_dataframe(df)
            return DataFetcher._extract_metrics(df)
            
        except Exception as e:
            print(f"A股指数获取失败 ({code}): {e}")
            return None

@st.cache_data(ttl=Config.CACHE_TTL)
def fetch_index_data(name: str, symbol: str) -> Optional[Dict]:
    """
    统一的数据获取入口
    根据指数类型自动选择合适的数据源
    """
    try:
        # 特殊处理：中概互联
        if name == "中概互联":
            pro = TushareClient.get_instance()
            
            # 优先使用Tushare
            if pro:
                result = DataFetcher.fetch_zhonggai_tushare(pro)
                if result:
                    return result
            
            # 降级到ETF方案（不再需要校准参数）
            return DataFetcher.fetch_zhonggai_etf()
        
        # 港股指数
        if symbol.startswith("hk"):
            return DataFetcher.fetch_hongkong_index(symbol)
        
        # 美股指数
        if symbol.startswith("gb"):
            return DataFetcher.fetch_us_index(symbol)
        
        # A股指数
        return DataFetcher.fetch_a_share_index(symbol)
        
    except Exception as e:
        print(f"[{name}] 数据获取失败: {e}")
        return None

# ================================
# UI 组件
# ================================
class UIComponents:
    """UI组件库"""
    
    @staticmethod
    def render_progress_bar(cur: float, lv: float, ld: str, hv: float, hd: str, sup: float, atm: float):
        """渲染进度条（优化版，防止标签重叠，支持移动端）"""
        # 检测是否为移动设备
        is_mobile = st.session_state.get('_is_mobile', False)
        
        axis_min = lv
        axis_max = max(hv, atm, cur) * 1.01
        total_range = axis_max - axis_min if axis_max > axis_min else 1
        
        def get_percent(value):
            return min(max((value - axis_min) / total_range * 100, 0), 100)
        
        cur_pct = get_percent(cur)
        sup_pct = get_percent(sup)
        atm_pct = get_percent(atm)
        high_pct = get_percent(hv)
        
        # 智能调整标签位置避免重叠
        labels = [
            {'pos': 0, 'type': 'low', 'value': lv, 'date': ld},
            {'pos': sup_pct, 'type': 'support', 'value': sup},
            {'pos': atm_pct, 'type': 'atm', 'value': atm},
            {'pos': high_pct, 'type': 'high', 'value': hv, 'date': hd}
        ]
        
        # 检测碰撞并调整垂直偏移
        for i in range(len(labels)):
            labels[i]['offset'] = 0
            if i > 0 and abs(labels[i]['pos'] - labels[i-1]['pos']) < 10:
                labels[i]['offset'] = 30 if labels[i-1]['offset'] == 0 else 0
        
        # 移动端调整：缩小字体和间距
        if is_mobile:
            font_scale = 0.85
            padding = "10px 15px 70px 15px"
            bar_height = 24
        else:
            font_scale = 1.0
            padding = "15px 30px 80px 30px"
            bar_height = 28
        
        html = f"""
        <div style="font-family:sans-serif; padding:{padding}; position:relative;">
            <div style="position:relative; height:140px; width:100%;">
                <!-- 进度条主体 -->
                <div style="display:flex; height:{bar_height}px; width:100%; border-radius:5px; overflow:hidden; border:1px solid #bbb; position:absolute; top:50px;">
                    <div style="width:{sup_pct:.1f}%; background:linear-gradient(90deg, #00f5d4, #00d4aa);"></div>
                    <div style="width:{max(0, atm_pct-sup_pct):.1f}%; background:linear-gradient(90deg, #fee440, #ffd700);"></div>
                    <div style="flex-grow:1; background:linear-gradient(90deg, #ffdce0, #ffb3ba);"></div>
                </div>
                
                <!-- 5年最低 -->
                <div style="position:absolute; left:0%; top:{45+labels[0]['offset']}px; height:35px; border-left:2px dashed #666;"></div>
                <div style="position:absolute; left:0%; top:{85+labels[0]['offset']}px; transform:translateX(-50%); text-align:center; font-size:{int(10*font_scale)}px; color:#555; width:{int(90*font_scale)}px; line-height:1.3; background:rgba(255,255,255,0.95); padding:3px; border-radius:3px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                    <b style="font-size:{int(11*font_scale)}px;">{lv:.0f}</b><br>
                    <span style="color:#888; font-size:{int(9*font_scale)}px;">最低 {ld}</span>
                </div>
                
                <!-- 支撑位 -->
                <div style="position:absolute; left:{sup_pct:.1f}%; top:{40+labels[1]['offset']}px; height:40px; border-left:3px solid #00aa55; z-index:5;"></div>
                <div style="position:absolute; left:{sup_pct:.1f}%; top:{85+labels[1]['offset']}px; transform:translateX(-50%); text-align:center; font-size:{int(11*font_scale)}px; color:#00aa55; font-weight:bold; width:{int(75*font_scale)}px; background:rgba(255,255,255,0.98); padding:4px; border-radius:4px; border:2px solid #00aa55; box-shadow:0 2px 4px rgba(0,170,85,0.2);">
                    <b>{sup:.0f}</b><br>
                    <span style="font-size:{int(9*font_scale)}px;">支撑位</span>
                </div>
                
                <!-- 大气层 -->
                <div style="position:absolute; left:{atm_pct:.1f}%; top:{40+labels[2]['offset']}px; height:40px; border-left:3px solid #ff3333; z-index:5;"></div>
                <div style="position:absolute; left:{atm_pct:.1f}%; top:{85+labels[2]['offset']}px; transform:translateX(-50%); text-align:center; font-size:{int(11*font_scale)}px; color:#ff3333; font-weight:bold; width:{int(75*font_scale)}px; background:rgba(255,255,255,0.98); padding:4px; border-radius:4px; border:2px solid #ff3333; box-shadow:0 2px 4px rgba(255,51,51,0.2);">
                    <b>{atm:.0f}</b><br>
                    <span style="font-size:{int(9*font_scale)}px;">大气层</span>
                </div>
                
                <!-- 5年最高 -->
                <div style="position:absolute; left:{high_pct:.1f}%; top:{45+labels[3]['offset']}px; height:35px; border-left:2px dashed #666;"></div>
                <div style="position:absolute; left:{high_pct:.1f}%; top:{85+labels[3]['offset']}px; transform:translateX(-50%); text-align:center; font-size:{int(10*font_scale)}px; color:#555; width:{int(90*font_scale)}px; line-height:1.3; background:rgba(255,255,255,0.95); padding:3px; border-radius:3px; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                    <b style="font-size:{int(11*font_scale)}px;">{hv:.0f}</b><br>
                    <span style="color:#888; font-size:{int(9*font_scale)}px;">最高 {hd}</span>
                </div>
                
                <!-- 当前点位指示器 -->
                <div style="position:absolute; left:{cur_pct:.1f}%; top:45px; transform:translateX(-50%); z-index:20; text-align:center;">
                    <div style="width:3px; height:40px; background:#000; margin:0 auto; box-shadow:0 0 4px rgba(0,0,0,0.4);"></div>
                    <div style="font-size:{int(14*font_scale)}px; font-weight:bold; background:#000; color:#fff; padding:5px 12px; border-radius:5px; margin-top:8px; white-space:nowrap; display:inline-block; box-shadow:0 3px 6px rgba(0,0,0,0.3); position:relative;">
                        {cur:.2f}
                        <div style="position:absolute; top:-6px; left:50%; transform:translateX(-50%); width:0; height:0; border-left:6px solid transparent; border-right:6px solid transparent; border-bottom:6px solid #000;"></div>
                    </div>
                </div>
            </div>
        </div>
        """
        st.components.v1.html(html, height=230)
    
    @staticmethod
    def render_sidebar():
        """渲染侧边栏"""
        with st.sidebar:
            st.title("🛠 系统控制面板")
            
            # Tushare状态
            pro = TushareClient.get_instance()
            if pro:
                st.success("✅ Tushare已连接")
                st.caption("中概互联使用官方数据")
            else:
                st.warning("⚠️ Tushare未配置")
                st.caption("中概互联使用ETF数据")
                with st.expander("📝 如何配置Tushare"):
                    st.markdown("""
**本地开发：**
```python
# 方法1：设置环境变量
# Windows (cmd):
set TUSHARE_TOKEN=你的token

# Mac/Linux:
export TUSHARE_TOKEN=你的token

# 方法2：创建 .streamlit/secrets.toml
TUSHARE_TOKEN = "你的token"
```

**Streamlit Cloud部署：**
1. 部署时点击 "Advanced settings"
2. 在 "Secrets" 中添加：
   ```
   TUSHARE_TOKEN = "你的token"
   ```
                    """)
            
            st.divider()
            
            # 操作按钮
            if st.button("🔄 强制刷新数据", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
            
            if st.button("💾 手动备份数据", use_container_width=True):
                DataManager.save(st.session_state.db)
                st.success("磁盘写入成功!")
            
            st.divider()
            st.info("💡 修改支撑位、大气层或日志时系统会自动保存。")
    
    @staticmethod
    def render_index_card(name: str, code: str, data: Dict):
        """渲染单个指数卡片"""
        st.subheader(f"📍 {name}")
        
        # 检测是否为移动设备（通过屏幕宽度判断）
        is_mobile = st.session_state.get('_is_mobile', False)
        
        # 根据设备类型调整布局比例
        if is_mobile:
            # 移动端：垂直布局
            UIComponents._render_parameters(name, data)
            st.divider()
            
            supports = st.session_state.db["supports"]
            atmospheres = st.session_state.db["atmospheres"]
            
            UIComponents.render_progress_bar(
                data['cur'], data['lv'], data['ld'], 
                data['hv'], data['hd'],
                supports[name], atmospheres[name]
            )
            
            UIComponents._render_notes_section(name)
        else:
            # 桌面端：左右布局
            col_left, col_right = st.columns([1, 4])
            
            with col_left:
                UIComponents._render_parameters(name, data)
            
            with col_right:
                supports = st.session_state.db["supports"]
                atmospheres = st.session_state.db["atmospheres"]
                
                UIComponents.render_progress_bar(
                    data['cur'], data['lv'], data['ld'], 
                    data['hv'], data['hd'],
                    supports[name], atmospheres[name]
                )
                
                UIComponents._render_notes_section(name)
        
        st.divider()
    
    @staticmethod
    def _render_parameters(name: str, data: Dict):
        """渲染参数设置区域"""
        cur_sup = float(st.session_state.db["supports"].get(name, 3000))
        cur_atm = float(st.session_state.db["atmospheres"].get(name, cur_sup * 1.3))
        
        new_sup = st.number_input("支撑位", value=cur_sup, key=f"sup_{name}")
        new_atm = st.number_input("大气层", value=cur_atm, key=f"atm_{name}")
        
        # 自动保存
        if new_sup != cur_sup or new_atm != cur_atm:
            st.session_state.db["supports"][name] = new_sup
            st.session_state.db["atmospheres"][name] = new_atm
            DataManager.save(st.session_state.db)
        
        # 显示当前点位和涨跌幅
        distance = ((data['cur'] - new_sup) / new_sup) * 100
        color = "#FF4B4B" if data['cur'] >= new_sup else "#21C354"
        arrow = "▲" if data['cur'] >= new_sup else "▼"
        
        st.markdown("**最新点位**")
        st.markdown(f"<div style='font-size:28px; font-weight:bold;'>{data['cur']:.2f}</div>", 
                   unsafe_allow_html=True)
        st.markdown(f"<div style='color:{color}; font-size:16px;'>{arrow} {distance:+.2f}%</div>", 
                   unsafe_allow_html=True)
        
        # 中概互联数据源提示
        if name == "中概互联":
            if data.get("source") == "Tushare":
                st.caption("✅ 数据源: Tushare官方")
            elif data.get("source") == "ETF":
                st.caption("💡 数据源: ETF备用")
                st.caption("⚠️ 建议配置Tushare获取官方数据")
    
    @staticmethod
    def _render_notes_section(name: str):
        """渲染策略日志区域"""
        notes_count = len(st.session_state.db["notes"].get(name, []))
        
        # 使用唯一的expander key，并从session_state读取展开状态
        expander_key = f"expander_{name}"
        if expander_key not in st.session_state:
            st.session_state[expander_key] = False
        
        with st.expander(f"💬 策略日志管理 ({notes_count}条)", expanded=st.session_state[expander_key]):
            # 添加日志表单
            with st.form(key=f"note_form_{name}", clear_on_submit=True):
                col_date, col_content, col_submit = st.columns([1.2, 3.5, 0.8])
                
                with col_date:
                    date_input = st.date_input("日期", datetime.now(), label_visibility="collapsed")
                with col_content:
                    content_input = st.text_input("心得", placeholder="在此记录策略...", 
                                                  label_visibility="collapsed")
                with col_submit:
                    submitted = st.form_submit_button("➕提交", use_container_width=True)
                
                if submitted and content_input.strip():
                    if name not in st.session_state.db["notes"]:
                        st.session_state.db["notes"][name] = []
                    
                    st.session_state.db["notes"][name].append({
                        "date": str(date_input),
                        "content": content_input.strip()
                    })
                    st.session_state.db["notes"][name].sort(key=lambda x: x['date'], reverse=True)
                    DataManager.save(st.session_state.db)
                    
                    # 保持expander展开状态
                    st.session_state[expander_key] = True
                    st.success("✅ 日志已添加")
                    # 不使用st.rerun()，避免页面跳动
            
            st.divider()
            
            # 显示日志列表
            UIComponents._render_notes_list(name)
    
    @staticmethod
    def _render_notes_list(name: str):
        """渲染日志列表"""
        if name not in st.session_state.db["notes"]:
            return
            
        notes_list = st.session_state.db["notes"][name]
        notes_list.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        for idx, note in enumerate(notes_list):
            # 使用稳定的索引key
            unique_key = f"{name}_note_{idx}"
            edit_mode_key = f"edit_mode_{unique_key}"
            is_editing = st.session_state.get(edit_mode_key, False)
            
            if not is_editing:
                # 查看模式
                cols = st.columns([1.2, 3.8, 0.4, 0.4])
                cols[0].write(f"📅 {note['date']}")
                cols[1].info(note['content'])
                
                if cols[2].button("📝", key=f"btn_edit_{unique_key}", use_container_width=True):
                    # 保存当前滚动位置
                    st.markdown("""
                        <script>
                        sessionStorage.setItem('scrollPos', window.scrollY);
                        </script>
                    """, unsafe_allow_html=True)
                    st.session_state[edit_mode_key] = True
                    st.rerun()
                
                if cols[3].button("🗑️", key=f"btn_del_{unique_key}", use_container_width=True):
                    # 保存当前滚动位置
                    st.markdown("""
                        <script>
                        sessionStorage.setItem('scrollPos', window.scrollY);
                        </script>
                    """, unsafe_allow_html=True)
                    st.session_state.db["notes"][name].pop(idx)
                    DataManager.save(st.session_state.db)
                    st.rerun()
            else:
                # 编辑模式 - 使用form来处理保存
                st.write(f"📅 {note['date']}")
                
                # 为每个编辑项创建独立的form
                with st.form(key=f"edit_form_{unique_key}", clear_on_submit=False):
                    edited_content = st.text_area(
                        "编辑内容", 
                        value=note['content'], 
                        height=100,
                        label_visibility="collapsed",
                        key=f"textarea_{unique_key}"
                    )
                    
                    col_save, col_cancel = st.columns([1, 1])
                    
                    save_clicked = col_save.form_submit_button("💾 保存", use_container_width=True)
                    cancel_clicked = col_cancel.form_submit_button("❌ 取消", use_container_width=True)
                
                # form外部处理提交逻辑（这很重要！）
                if save_clicked:
                    if edited_content.strip():
                        # 保存当前滚动位置
                        st.markdown("""
                            <script>
                            sessionStorage.setItem('scrollPos', window.scrollY);
                            </script>
                        """, unsafe_allow_html=True)
                        # 直接修改原始数据
                        st.session_state.db["notes"][name][idx]['content'] = edited_content.strip()
                        st.session_state[edit_mode_key] = False
                        DataManager.save(st.session_state.db)
                        st.success("✅ 修改已保存")
                        st.rerun()
                
                if cancel_clicked:
                    # 保存当前滚动位置
                    st.markdown("""
                        <script>
                        sessionStorage.setItem('scrollPos', window.scrollY);
                        </script>
                    """, unsafe_allow_html=True)
                    st.session_state[edit_mode_key] = False
                    st.rerun()
            
            if idx < len(notes_list) - 1:
                st.markdown("---")

# ================================
# 主应用入口
# ================================
def main():
    """主应用程序"""
    # 页面配置 - 必须在最前面
    st.set_page_config(
        layout="wide", 
        page_title="投资策略监控",
        initial_sidebar_state="auto"  # 移动端自动折叠侧边栏
    )
    
    # 初始化数据
    if 'db' not in st.session_state:
        st.session_state.db = DataManager.load()
    
    # 检测设备类型（通过JavaScript传递）
    st.markdown("""
        <script>
        // 检测是否为移动设备
        function isMobileDevice() {
            return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) 
                   || window.innerWidth <= 768;
        }
        
        // 通过修改body的data属性来传递设备信息
        if (isMobileDevice()) {
            document.body.setAttribute('data-device', 'mobile');
        } else {
            document.body.setAttribute('data-device', 'desktop');
        }
        </script>
    """, unsafe_allow_html=True)
    
    # 简单的移动端检测（基于Streamlit的viewport）
    # 这是一个启发式方法，因为Streamlit不直接提供设备检测
    if '_is_mobile' not in st.session_state:
        st.session_state._is_mobile = False  # 默认为桌面端
    
    # 自定义CSS
    st.markdown("""
        <style>
        div[data-testid="stExpander"] { 
            border: none !important; 
            box-shadow: none !important; 
            margin-left: 20px !important; 
            margin-right: 20px !important; 
        }
        [data-testid="column"] { padding: 0px 10px !important; }
        html {
            scroll-behavior: auto !important;
        }
        /* 防止rerun时页面滚动 */
        html, body {
            overflow-anchor: none !important;
        }
        
        /* 移动端适配 */
        @media (max-width: 768px) {
            /* 缩小标题字体 */
            h1 { font-size: 1.5rem !important; }
            h2 { font-size: 1.2rem !important; }
            h3 { font-size: 1rem !important; }
            
            /* 调整expander间距 */
            div[data-testid="stExpander"] {
                margin-left: 5px !important;
                margin-right: 5px !important;
            }
            
            /* 缩小侧边栏宽度 */
            section[data-testid="stSidebar"] {
                width: 280px !important;
            }
            
            /* 调整列间距 */
            [data-testid="column"] { 
                padding: 0px 5px !important; 
            }
            
            /* 缩小按钮 */
            button {
                font-size: 0.85rem !important;
                padding: 0.3rem 0.6rem !important;
            }
            
            /* 优化输入框 */
            input, textarea {
                font-size: 0.9rem !important;
            }
            
            /* 缩小进度条高度 */
            .stProgress > div > div {
                height: 0.3rem !important;
            }
        }
        </style>
        <script>
        // 检测设备类型
        function detectDevice() {
            const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
            const isSmallScreen = window.innerWidth <= 768;
            return isMobile || isSmallScreen;
        }
        
        // 存储设备类型到sessionStorage
        sessionStorage.setItem('isMobile', detectDevice());
        
        // 保存当前滚动位置
        window.addEventListener('beforeunload', function() {
            sessionStorage.setItem('scrollPos', window.scrollY);
        });
        
        // 页面加载后恢复滚动位置
        window.addEventListener('load', function() {
            const scrollPos = sessionStorage.getItem('scrollPos');
            if (scrollPos) {
                window.scrollTo(0, parseInt(scrollPos));
            }
        });
        
        // Streamlit rerun时保持滚动位置
        const observer = new MutationObserver(function() {
            const scrollPos = sessionStorage.getItem('scrollPos');
            if (scrollPos) {
                window.scrollTo(0, parseInt(scrollPos));
                sessionStorage.removeItem('scrollPos');
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
        </script>
    """, unsafe_allow_html=True)
    
    # 渲染侧边栏
    UIComponents.render_sidebar()
    
    # 主标题 - 添加设备切换按钮
    col_title, col_toggle = st.columns([4, 1])
    with col_title:
        st.title("📊 指数监控及策略管理")
    with col_toggle:
        # 设备模式切换（用于测试和手动切换）
        if st.button("📱/💻", help="切换移动/桌面模式"):
            st.session_state._is_mobile = not st.session_state.get('_is_mobile', False)
            st.rerun()
    
    # 显示当前模式提示
    if st.session_state.get('_is_mobile', False):
        st.caption("📱 移动端模式 - 垂直布局")
    else:
        st.caption("💻 桌面端模式 - 左右布局")
    
    # 遍历所有分组
    for group_name, indices in Config.INDEX_GROUPS.items():
        with st.expander(f"### {group_name}", expanded=True):
            for index_name, index_code in indices.items():
                data = fetch_index_data(index_name, index_code)
                
                if data:
                    UIComponents.render_index_card(index_name, index_code, data)
                else:
                    st.error(f"❌ {index_name} 数据暂不可用，请尝试点击侧边栏刷新。")

if __name__ == "__main__":
    main()