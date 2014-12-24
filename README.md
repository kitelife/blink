### 简介

通常，服务器监控系统分为**客户端**和**服务器端**两部分，**客户端**负责对服务器的各种指标进行数据采样并发送给**服务器端**，
**服务器端**接收**客户端**发送来的数据，存入数据库等用于展示分析。

但如果你只有一台服务器，或者对于创业公司来说，不想在监控系统上花太多精力和money，那么常见的监控系统就不太适用，可能**blink**正是你所需要的。

监控系统按照不同的层面和方面分为很多种：进程监控/管理、服务器性能指标（如CPU、内存等）监控/告警、服务器可用性监控、业务数据监控等

**blink**解决的是`服务器性能指标（如CPU、内存等）监控/告警`。

### 原理

对于CPU、内存，blink会定期（固定时间间隔interval）采样使用率数据，存入sqlite数据库中。每次得到采样数据后，会判断是否有连续N次使用率
超过了设定的阈值，如果是，则会发送告警邮件。

对于磁盘，blink会有一个进程定期检测各个挂载点/分区的使用率，如果某些挂载点的使用率超过了阈值，则会发送告警邮件。

另一个进程会定期从sqlite数据库中查询到CPU、内存使用率数据，如果配置的邮件类型`email_type`为**basic**，则对CPU、内存分别
取最大的n个数据点（包含采样时的时间），发送概要邮件；

如果邮件类型为**advanced**，则将CPU、内存使用率分别根据时间绘制成图，并发送概要邮件。

概要邮件中处理CPU、内存使用率的信息，还包含服务器的基本信息，如开机时间（通过开机时间可以判断服务器是否曾经自动重启过）；此外还包含磁盘的使用率数据。

------

CPU、内存使用率数据绘图过程是先通过vincent将图形的数据存入一个json文件中，然后使用vega提供的工具`vg2png`生成png图片。

### 配置说明

```
config = {
    # 概要邮件内容类型，basic代表邮件内容中CPU、内存使用率的信息只包含最大的n个数据点，advanced则表示将使用率数据绘制成图，然后通过邮件发送图片
    'email_type': 'basic',  # or advanced
    # 当前服务器的外网ip，概要邮件中用到
    'host_ip': '',
    # cpu指标监控相关配置
    'cpu': {
        # 采样间隔
        'interval': 1,
        # CPU使用率的最大阈值
        'threshold': 90,
    },
    # cpu指标监控相关配置
    'mem': {
        'interval': 1,
        'threshold': 90,
    },
    # cpu指标监控相关配置
    'disk': {
        # 由于磁盘的使用率变化很慢，所以interval可以设置成大些
        'interval': 10,
        'threshold': 90,
    },
    # 概要邮件进程相关的配置信息
    'email': {
        # 发送概要邮件的时间间隔，通常为12小时一次、24小时一次等
        'interval': 300,
        # 邮件服务器的相关信息
        'server': {
            'host': '',
            'port': 465,
            'username': '',
            'password': '',
        },
        # 邮件发送者
        'from': '',
        # 邮件接收者，注意可以有多个
        'to': [''],
    }
}
```

### 依赖

- psutil: http://pythonhosted.org/psutil/
- jinja2：http://jinja.pocoo.org/

可选依赖：

- vincent：https://vincent.readthedocs.org/en/latest/
- pandas：http://pandas.pydata.org/
- vega：https://vincent.readthedocs.org/en/latest/

##### 依赖安装

- `pip install psutil jinja2`

如果配置文件中`email_type`一项设置为“advanced”，即表示选择图表形式的邮件内容，则需要额外安装

- `pip install pandas vincent`
- 安装nodejs、npm
- 如果是Debian系的Linux发行版，执行`sudo apt-get install libcairo2-dev libjpeg8-dev libpango1.0-dev libgif-dev build-essential g++`，其他操作系统需要的操作见[这里](https://github.com/Automattic/node-canvas/wiki/_pages)
- 在blink根目录下执行`git clone https://github.com/trifacta/vega.git`
- `cd vega && npm install`