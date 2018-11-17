#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# https://qiita.com/rukihena/items/82266ed3a43e4b652adb

# 2018-11-17 Modified by shima@shakemid.com
#            To be able to run with python 3

#from __future__ import print_function

import sys
import serial
import time
import os
import configparser

# Config読み込み
config = configparser.ConfigParser()
config.read(os.path.dirname(__file__) + '/config.ini', 'UTF-8')

rbid  = config.get('config', 'rbid')
rbpwd = config.get('config', 'rbpwd')
serialPortDev = config.get('config', 'serialPortDev')

# シリアルポート初期化
ser = serial.Serial(serialPortDev, 115200)

# とりあえずバージョンを取得してみる（やらなくてもおｋ）
cmd = "SKVER\r\n"
ser.write(cmd.encode())
print(ser.readline()) # エコーバック
print(ser.readline()) # バージョン

# Bルート認証パスワード設定
cmd = "SKSETPWD C " + rbpwd + "\r\n"
ser.write(cmd.encode())
print(ser.readline()) # エコーバック
print(ser.readline()) # OKが来るはず（チェック無し）

# Bルート認証ID設定
cmd = "SKSETRBID " + rbid + "\r\n"
ser.write(cmd.encode())
print(ser.readline()) # エコーバック
print(ser.readline()) # OKが来るはず（チェック無し）

scanDuration = 4;   # スキャン時間。サンプルでは6なんだけど、4でも行けるので。（ダメなら増やして再試行）
scanRes = {} # スキャン結果の入れ物

# スキャンのリトライループ（何か見つかるまで）
while not 'Channel' in scanRes.keys() :
    # アクティブスキャン（IE あり）を行う
    # 時間かかります。10秒ぐらい？
    cmd = "SKSCAN 2 FFFFFFFF " + str(scanDuration) + "\r\n"
    ser.write(cmd.encode())

    # スキャン1回について、スキャン終了までのループ
    scanEnd = False
    while not scanEnd :
        line = ser.readline()
        print(line)

        if line.startswith(b"EVENT 22") :
            # スキャン終わったよ（見つかったかどうかは関係なく）
            scanEnd = True
        elif line.startswith(b"  ") :
            # スキャンして見つかったらスペース2個あけてデータがやってくる
            # 例
            #  Channel:39
            #  Channel Page:09
            #  Pan ID:FFFF
            #  Addr:FFFFFFFFFFFFFFFF
            #  LQI:A7
            #  PairID:FFFFFFFF
            cols = line.decode().strip().split(':')
            scanRes[cols[0]] = cols[1]
    scanDuration+=1

    if 7 < scanDuration and not 'Channel' in scanRes.keys() :
        # 引数としては14まで指定できるが、7で失敗したらそれ以上は無駄っぽい
        print("スキャンリトライオーバー")
        sys.exit(1)  #### 糸冬了 ####

# スキャン結果からChannelを設定。
cmd = "SKSREG S2 " + scanRes["Channel"] + "\r\n"
ser.write(cmd.encode())
print(ser.readline()) # エコーバック
print(ser.readline()) # OKが来るはず（チェック無し）

# スキャン結果からPan IDを設定
cmd = "SKSREG S3 " + scanRes["Pan ID"] + "\r\n"
ser.write(cmd.encode())
print(ser.readline()) # エコーバック
print(ser.readline()) # OKが来るはず（チェック無し）

# MACアドレス(64bit)をIPV6リンクローカルアドレスに変換。
# (BP35A1の機能を使って変換しているけど、単に文字列変換すればいいのではという話も？？)
cmd = "SKLL64 " + scanRes["Addr"] + "\r\n"
ser.write(cmd.encode())
print(ser.readline()) # エコーバック
ipv6Addr = ser.readline().decode().strip()
print(ipv6Addr)

# PANA 接続シーケンスを開始します。
cmd = "SKJOIN " + ipv6Addr + "\r\n"
ser.write(cmd.encode())
print(ser.readline()) # エコーバック
print(ser.readline()) # OKが来るはず（チェック無し）

# PANA 接続完了待ち（10行ぐらいなんか返してくる）
bConnected = False
while not bConnected :
    line = ser.readline()
    print(line)
    if line.startswith(b"EVENT 24") :
        print("PANA 接続失敗")
        sys.exit(1)  #### 糸冬了 ####
    elif line.startswith(b"EVENT 25") :
        # 接続完了！
        bConnected = True

# これ以降、シリアル通信のタイムアウトを設定
ser.timeout = 10

# スマートメーターがインスタンスリスト通知を投げてくる
# (ECHONET-Lite_Ver.1.12_02.pdf p.4-16)
print(ser.readline()) #無視

# ECHONET Lite フレーム作成
# 　参考資料
# 　・ECHONET-Lite_Ver.1.12_02.pdf (以下 EL)
# 　・Appendix_H.pdf (以下 AppH)
echonetLiteFrame = b""
echonetLiteFrame += b"\x10\x81"      # EHD (参考:EL p.3-2)
echonetLiteFrame += b"\x00\x01"      # TID (参考:EL p.3-3)
# ここから EDATA
echonetLiteFrame += b"\x05\xFF\x01"  # SEOJ (参考:EL p.3-3 AppH p.3-408〜)
echonetLiteFrame += b"\x02\x88\x01"  # DEOJ (参考:EL p.3-3 AppH p.3-274〜)
echonetLiteFrame += b"\x62"          # ESV(62:プロパティ値読み出し要求) (参考:EL p.3-5)
echonetLiteFrame += b"\x01"          # OPC(1個)(参考:EL p.3-7)
echonetLiteFrame += b"\xE7"          # EPC(参考:EL p.3-7 AppH p.3-275)
echonetLiteFrame += b"\x00"          # PDC(参考:EL p.3-9)

# コマンド送信
command = "SKSENDTO 1 {0} 0E1A 1 {1:04X} ".format(ipv6Addr, len(echonetLiteFrame)).encode() + echonetLiteFrame + "\r\n".encode()
print(command)
ser.write(command)

print(ser.readline()) # エコーバック
print(ser.readline()) # EVENT 21 が来るはず（チェック無し）
print(ser.readline()) # OKが来るはず（チェック無し）
print(ser.readline()) # 改行が来るはず（チェック無し）

line = ser.readline() # ERXUDPが来るはず
print(line)

# 受信データはたまに違うデータが来たり、
# 取りこぼしたりして変なデータを拾うことがあるので
# チェックを厳しめにしてます。
if line.startswith(b"ERXUDP") :
    cols = line.decode().strip().split(' ')
    res = cols[8]   # UDP受信データ部分
    #tid = res[4:4+4];
    seoj = res[8:8+6]
    #deoj = res[14,14+6]
    ESV = res[20:20+2]
    #OPC = res[22,22+2]
    if seoj == "028801" and ESV == "72" :
        # スマートメーター(028801)から来た応答(72)なら
        EPC = res[24:24+2]
        if EPC == "E7" :
            # 内容が瞬時電力計測値(E7)だったら
            hexPower = line[-8:]    # 最後の4バイト（16進数で8文字）が瞬時電力計測値
            intPower = int(hexPower, 16)
            print(u"瞬時電力計測値: {0} [W]".format(intPower))
else :
    print("不明なデータを受信")
    sys.exit(1)

ser.close()
sys.exit(0)
