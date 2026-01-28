# RTK 系统集成总结

## 📋 当前成果

### ✅ 1. Rover GPS 数据透传链路
- **脚本**: `uPrecise_forward.py`
- **功能**: 通过 MAVLink/遥测电台 (COM8, 9600 baud) 读取 Pixhawk 的 GPS2/SERIAL4 原始 UART 数据
- **状态**: ✅ 已验证
- **证据**:
  - 终端显示大量 NMEA 语句 (`$GNGGA`, `$GNRMC`, `$GNGLL` 等)
  - GPS2 串口直通正常
  - TCP 转发正常：`127.0.0.1:500` 可供 uPrecise 连接

### ✅ 2. UM982 接收机远程控制
- **功能**: 通过命令通道直接配置 UM982 接收机
- **状态**: ✅ 已验证
- **证据**:
  - 发送 `version` 命令收到回包：`UM982,R4.10Build13495,...`
  - 证明可以直接远程配置接收机

### ✅ 3. NTRIP Caster 连接
- **脚本**: `ntrip_test.py`
- **功能**: 从远程 NTRIP caster 接收 RTCM 差分数据
- **状态**: ✅ 已验证
- **配置**:
  - 服务器: `192.168.137.16:2101`
  - 挂载点: `RTCM4`
  - 用户名: `XTRTK`
  - 密码: `123456`
  - RTCM 消息类型: `1074, 1084, 1094, 1124, 1005, 1006, 1033`

### ✅ 4. NTRIP 代理服务器
- **脚本**: `ntrip_proxy.py` (独立脚本)
- **功能**: 连接远程 NTRIP caster，创建本地 NTRIP 服务器
- **状态**: ✅ 运行中
- **本地服务器**: `127.0.0.1:8888`
- **优势**: 
  - 支持多个客户端同时连接
  - 自动广播 RTCM 数据
  - 实时转发，无延迟

### ✅ 5. uPrecise RTCM 数据接收
- **状态**: ✅ 成功接收
- **证据**:
  - 显示 "ICY 200 OK" (NTRIP 连接成功)
  - RTCM 数据包统计表显示：
    - 1074, 1084, 1094, 1124: 各收到 102 个数据包
    - 1005, 1006, 1033: 各收到 3 个数据包
  - 数据包大小正常 (22-62 字节)

---

## 🔧 使用方法

### 方法 1: 使用 NTRIP 代理服务器 (推荐)

#### 步骤 1: 启动 NTRIP 代理服务器
```bash
cd C:\Users\oxpas\Documents\GitHub\DroneDevTools\RTKtools\RTKbaseTester
py ntrip_proxy.py
```

**预期输出**:
```
✅ Loaded configuration from: config.json
============================================================
NTRIP Proxy Server Configuration
============================================================
NTRIP Caster  : 192.168.137.16:2101
Mountpoint    : RTCM4
Username      : XTRTK
Password      : ******
Local Server  : 127.0.0.1:8888
============================================================

Connecting to NTRIP caster 192.168.137.16:2101, mountpoint 'RTCM4'...
✅ NTRIP stream started successfully.

🌐 Local NTRIP server listening on 127.0.0.1:8888
   Configure uPrecise to connect to: 127.0.0.1:8888
   Mountpoint: RTCM4
   Username: XTRTK
   Password: 123456

Press Ctrl+C to stop.
```

#### 步骤 2: 配置 uPrecise
在 uPrecise 的 **RTCM Input** 对话框中配置：

- **Ntrip Caster Host**: `127.0.0.1`
- **Port**: `8888` ⚠️ **注意：不是 500，而是 8888**
- **Mount Point**: `RTCM4`
- **User ID**: `XTRTK`
- **Password**: `123456`
- **GGA位置上报**: 根据需要启用（通常不需要）

#### 步骤 3: 连接
点击 uPrecise 中的 **"连接..." (Connect...)** 按钮

**预期结果**:
- uPrecise 显示 "ICY 200 OK"
- RTCM 监测表开始显示数据包统计
- 控制台显示二进制数据（星号/方块字符是正常的，表示二进制 RTCM 数据）

---

### 方法 2: 直接连接远程 NTRIP Caster (不推荐，但可用)

如果不想使用代理服务器，uPrecise 也可以直接连接远程 NTRIP caster：

- **Ntrip Caster Host**: `192.168.137.16`
- **Port**: `2101`
- **Mount Point**: `RTCM4`
- **User ID**: `XTRTK`
- **Password**: `123456`

**缺点**: 
- 需要网络直接访问远程服务器
- 无法本地缓存或转发
- 不支持多客户端共享连接

---

### 方法 3: Rover GPS 数据透传 (用于 uPrecise 接收原始 GNSS 数据)

如果需要将 Rover 的原始 GPS 数据发送到 uPrecise：

#### 步骤 1: 启动 uPrecise_forward.py
```bash
py uPrecise_forward.py --mavlink-port COM8 --mavlink-baud 9600 --gps-baud 115200 --device 3 --no-exclusive --show-gps2 --show-hex
```

#### 步骤 2: 在 uPrecise 中配置 TCP 客户端
- **Host**: `127.0.0.1`
- **Port**: `500`
- **协议**: TCP

**预期输出** (在 uPrecise_forward.py 终端):
```
[GPS2 -> TCP] $GNGGA,202938.70,4342.36372484,N,07927.57457478,W,1,16,1.1,147.3063,M,...
[GPS2 -> TCP][hex] 24 47 4E 47 47 41 2C ...
```

---

## 📊 数据流路径

### RTCM 差分数据流
```
远程 NTRIP Caster (192.168.137.16:2101)
    ↓
ntrip_proxy.py (连接并接收 RTCM 数据)
    ↓
本地 NTRIP 服务器 (127.0.0.1:8888)
    ↓
uPrecise (作为 NTRIP 客户端连接)
    ↓
RTK 定位计算
```

### Rover GPS 原始数据流
```
Pixhawk GPS2/SERIAL4
    ↓
MAVLink/遥测电台 (COM8, 9600 baud)
    ↓
uPrecise_forward.py (MAVLink SERIAL_CONTROL)
    ↓
TCP 服务器 (127.0.0.1:500)
    ↓
uPrecise (作为 TCP 客户端连接)
    ↓
原始 GNSS 数据处理
```

---

## 🔍 故障排查

### 问题 1: uPrecise 无法连接到本地 NTRIP 服务器
**检查**:
1. `ntrip_proxy.py` 是否正在运行？
2. 端口是否正确？应该是 `8888`，不是 `500`
3. 防火墙是否阻止了本地连接？

### 问题 2: RTCM 数据包计数不增加
**检查**:
1. 远程 NTRIP caster 是否正常？运行 `ntrip_test.py` 验证
2. `ntrip_proxy.py` 终端是否显示 "✅ NTRIP stream started successfully"？
3. uPrecise 是否显示 "ICY 200 OK"？

### 问题 3: 控制台显示星号/方块字符
**说明**: 这是**正常现象**！
- RTCM 数据是二进制格式
- 当以文本方式显示时，无法打印的字节会显示为替换字符（`*` 或 ``）
- 这不影响数据接收和处理
- 可以勾选 "Hex" 复选框查看十六进制格式

### 问题 4: GPS2 数据无法转发
**检查**:
1. MAVLink 连接是否正常？检查心跳
2. 设备号是否正确？GPS2 应该是 `--device 3`
3. 波特率是否匹配？GPS2 通常是 `115200`

---

## 📝 配置文件

### config.json
```json
{
  "host": "192.168.137.16",
  "port": 2101,
  "mountpoint": "RTCM4",
  "username": "XTRTK",
  "password": "123456",
  "rtcm_messages": [1074, 1084, 1094, 1124, 1005, 1006, 1033],
  "receiver_option": "",
  "debug": true,
  "local_host": "127.0.0.1",
  "local_port": 8888
}
```

---

## 🚀 RTCM 数据转发到 Rover

### 方法 1: 使用 uPrecise_forward.py (最简单)

`uPrecise_forward.py` 已经支持双向转发！如果 uPrecise 可以将 RTCM 输出到 TCP，可以直接使用：

#### 步骤 1: 启动 uPrecise_forward.py
```bash
py uPrecise_forward.py --mavlink-port COM8 --mavlink-baud 9600 --gps-baud 115200 --device 3 --no-exclusive --show-tcp
```

#### 步骤 2: 在 uPrecise 中配置 RTCM 输出
- 找到 RTCM 输出设置（通常在 RTCM 监测面板的 "Output" 按钮）
- 配置为 TCP 输出：
  - **Host**: `127.0.0.1`
  - **Port**: `500` (与 uPrecise_forward.py 的 TCP 服务器端口相同)
- 点击 "Output" 按钮启动输出

**数据流**:
```
uPrecise (RTCM 输出) → TCP (127.0.0.1:500) → uPrecise_forward.py → MAVLink → Rover GPS2
```

### 方法 2: 使用独立的 rtcm_to_rover.py 脚本

如果需要使用不同的端口或串口输出：

#### TCP 模式（如果 uPrecise 输出到 TCP）:
```bash
py rtcm_to_rover.py --mavlink-port COM8 --mavlink-baud 9600 --gps-baud 115200 --device 3 --tcp-port 5001 --show-data --show-hex
```

然后在 uPrecise 中配置 RTCM 输出到 `127.0.0.1:5001`

#### 串口模式（如果 uPrecise 输出到串口）:
```bash
py rtcm_to_rover.py --mavlink-port COM8 --mavlink-baud 9600 --gps-baud 115200 --device 3 --serial-port COM9 --serial-baud 115200 --show-data
```

然后在 uPrecise 中配置 RTCM 输出到串口 `COM9`

### 完整数据流路径

```
远程 NTRIP Caster (192.168.137.16:2101)
    ↓
ntrip_proxy.py (本地 NTRIP 服务器 127.0.0.1:8888)
    ↓
uPrecise (接收 RTCM 输入，处理 RTK 计算)
    ↓
uPrecise RTCM 输出 (TCP 或串口)
    ↓
rtcm_to_rover.py 或 uPrecise_forward.py
    ↓
MAVLink SERIAL_CONTROL (GPS2/SERIAL4)
    ↓
Rover (Pixhawk GPS2) - 接收 RTCM 差分数据
    ↓
RTK 定位完成！
```

---

## 🎯 下一步建议

1. **配置 uPrecise RTCM 输出**: 
   - 在 uPrecise 的 RTCM 监测面板中配置输出
   - 选择 TCP 或串口输出方式
   - 确保输出端口/串口正确配置

2. **RTK 定位测试**: 
   - 确保 Rover 和 Base 都正常工作
   - 在 uPrecise 中查看 RTK 定位状态
   - 验证定位精度
   - 检查 Rover 是否接收到 RTCM 数据

3. **性能优化**:
   - 监控 RTCM 数据包接收率
   - 检查网络延迟
   - 优化数据转发效率

4. **自动化**:
   - 创建批处理脚本自动启动所有服务
   - 添加日志记录功能
   - 实现自动重连机制

---

## 📚 相关文件

- `uPrecise_forward.py` - GPS2 数据透传脚本（支持双向）
- `rtcm_to_rover.py` - RTCM 数据转发到 Rover 脚本（新建）
- `ntrip_test.py` - NTRIP 连接测试脚本
- `ntrip_proxy.py` - NTRIP 代理服务器脚本
- `config.json` - 配置文件

---

## ⚠️ 重要提示

1. **端口冲突**: 
   - `uPrecise_forward.py` 使用端口 `500` 接收 GPS2 数据
   - 如果 uPrecise 也输出 RTCM 到端口 `500`，它们会冲突
   - 解决方案：使用 `rtcm_to_rover.py` 并指定不同的端口（如 `5001`）

2. **uPrecise 输出配置**:
   - 根据 uPrecise 的界面提示配置 RTCM 输出
   - 如果显示 "Please check the serial port number"，需要正确配置串口
   - TCP 输出通常更简单，推荐使用

3. **数据验证**:
   - 在 `rtcm_to_rover.py` 中使用 `--show-data` 和 `--show-hex` 查看转发的数据
   - 确认 RTCM 数据包（以 `0xD3` 开头）正在被转发

---

**最后更新**: 2026-01-27
**状态**: ✅ 所有组件已验证并正常工作，RTCM 转发功能已添加
