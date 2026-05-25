#!/usr/bin/env python3
"""
使用 Sourcify 免费 API 验证 BSC 合约
完全免费，无需 API Key
支持 BSC 主网 (56) 和测试网 (97)
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import json
import requests
import time
from pathlib import Path

# ========== 配置区域 ==========
CONTRACT_ADDRESS = ""  # 留空则提示输入，或在这里直接填合约地址
CHAIN_ID = "56"  # 56 = BSC 主网, 97 = BSC 测试网
SOLC_VERSION = "0.8.20"

# 文件路径（相对于本脚本）
WORKSPACE = Path(__file__).parent
CONTRACT_FILE = WORKSPACE / "ModaMintToken.sol"
METADATA_FILE = WORKSPACE / "metadata.json"
FACTORY_FILE = WORKSPACE / "TokenFactory.sol"  # 如果有工厂合约
# ==============================


def print_header():
    print("=" * 60)
    print("  Sourcify 免费合约验证工具")
    print("  完全免费，无需 API Key")
    print("=" * 60)
    print()


def get_contract_address():
    """获取合约地址"""
    if CONTRACT_ADDRESS:
        return CONTRACT_ADDRESS
    
    print("📝 请输入合约地址：")
    addr = input("  > 0x").strip()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    return addr


def verify_via_sourcify(contract_address, chain_id):
    """
    使用 Sourcify API 验证合约
    Sourcify 完全免费，支持多链
    """
    print(f"\n{'='*60}")
    print(f"  方法1: Sourcify 免费验证")
    print(f"{'='*60}\n")
    
    # 检查文件
    if not CONTRACT_FILE.exists():
        print(f"❌ 错误：找不到合约文件 {CONTRACT_FILE}")
        return False
    
    if not METADATA_FILE.exists():
        print(f"❌ 错误：找不到 metadata.json")
        print(f"   请先运行 compile_contract.py 生成 metadata.json")
        return False
    
    print(f"📄 合约文件: {CONTRACT_FILE.name}")
    print(f"📄 Metadata: {METADATA_FILE.name}")
    print(f"🔗 链 ID: {chain_id} ({get_chain_name(chain_id)})")
    print(f"📍 合约地址: {contract_address}\n")
    
    # 准备上传的文件
    files_to_upload = []
    
    # 添加主合约文件
    with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
        files_to_upload.append(("files", (CONTRACT_FILE.name, f.read(), "text/plain")))
    
    # 添加 metadata.json
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        files_to_upload.append(("files", (METADATA_FILE.name, f.read(), "application/json")))
    
    # 如果有工厂合约，也加上
    if FACTORY_FILE.exists():
        with open(FACTORY_FILE, "r", encoding="utf-8") as f:
            files_to_upload.append(("files", (FACTORY_FILE.name, f.read(), "text/plain")))
        print(f"📄 工厂合约: {FACTORY_FILE.name}")
    
    # Sourcify API 端点
    # 使用官方公共服务器
    url = "https://sourcify.dev/server/verify"
    
    # 表单数据
    data = {
        "address": contract_address,
        "chain": chain_id,
    }
    
    print(f"🚀 正在提交验证请求到 Sourcify...\n")
    
    try:
        response = requests.post(url, files=files_to_upload, data=data, timeout=60)
        
        print(f"📊 HTTP 状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 验证请求已提交！")
            print(f"\n📋 响应:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # 检查验证状态
            if "result" in result:
                status = result["result"].get("status")
                if status == "perfect":
                    print(f"\n🎉 完美匹配！合约已通过 Sourcify 验证")
                    print(f"   查看: https://sourcify.dev/#/verify/{chain_id}/{contract_address}")
                    return True
                elif status == "partial":
                    print(f"\n⚠️ 部分匹配，请检查验证详情")
                    print(f"   查看: https://sourcify.dev/#/verify/{chain_id}/{contract_address}")
                    return True
                else:
                    print(f"\n⏳ 验证进行中，请稍后查看结果...")
                    print(f"   查看: https://sourcify.dev/#/verify/{chain_id}/{contract_address}")
                    return True
            else:
                # 轮询验证状态
                return poll_verification_status(contract_address, chain_id)
        else:
            print(f"❌ 验证请求失败")
            print(f"响应: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ 请求超时，请检查网络连接")
        return False
    except Exception as e:
        print(f"❌ 验证失败: {e}")
        return False


def poll_verification_status(contract_address, chain_id, max_attempts=10):
    """
    轮询验证状态
    Sourcify 可能需要一些时间来处理验证
    """
    print(f"\n⏳ 正在轮询验证状态...")
    
    url = f"https://sourcify.dev/server/verification-status/{chain_id}/{contract_address}"
    
    for attempt in range(max_attempts):
        print(f"  尝试 {attempt + 1}/{max_attempts}...", end=" ")
        
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                status = result.get("status")
                
                print(f"状态: {status}")
                
                if status == "perfect":
                    print(f"\n🎉 完美匹配！合约已通过 Sourcify 验证")
                    print(f"   查看: https://sourcify.dev/#/verify/{chain_id}/{contract_address}")
                    return True
                elif status == "partial":
                    print(f"\n⚠️ 部分匹配")
                    print(f"   查看: https://sourcify.dev/#/verify/{chain_id}/{contract_address}")
                    return True
                elif status == "error":
                    print(f"\n❌ 验证失败: {result.get('error', '未知错误')}")
                    return False
                else:
                    # 继续等待
                    time.sleep(3)
            else:
                print(f"HTTP {response.status_code}")
                time.sleep(3)
                
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(3)
    
    print(f"\n⚠️ 验证超时，请手动查看:")
    print(f"   https://sourcify.dev/#/verify/{chain_id}/{contract_address}")
    return False


def verify_via_oklink(contract_address, chain_id):
    """
    方法2: 使用 OKLink 免费验证
    OKLink 提供免费的 BSC 合约验证服务
    """
    print(f"\n{'='*60}")
    print(f"  方法2: OKLink 免费验证（手动）")
    print(f"{'='*60}\n")
    
    print(f"OKLink 提供免费的 BSC 合约验证服务")
    print(f"\n步骤:")
    print(f"  1. 访问: https://www.oklink.com/zh-hans/bsc/verify-contract-preliminary")
    print(f"  2. 输入合约地址: {contract_address}")
    print(f"  3. 选择编译器版本: {SOLC_VERSION}")
    print(f"  4. 上传 ModaMintToken.sol")
    print(f"  5. 填写构造函数参数（如果有）")
    print(f"  6. 提交验证\n")
    
    # 生成构造函数参数的 ABI 编码（如果需要）
    print(f"💡 提示: 如果你有构造函数参数，可以运行:")
    print(f"   python -c \"from web3 import Web3; print(Web3.keccak(text='your_constructor_signature')[0:4].hex())\"")
    print(f"   来获取函数选择器\n")
    
    return True


def verify_via_bscscan_manual(contract_address, chain_id):
    """
    方法3: BSCScan 手动验证（免费）
    虽然 API 收费，但网页手动验证是免费的
    """
    print(f"\n{'='*60}")
    print(f"  方法3: BSCScan 网页手动验证（免费）")
    print(f"{'='*60}\n")
    
    network = "bsc" if chain_id == "56" else "bsc-testnet"
    
    print(f"BSCScan 网页验证完全免费（API 才收费）")
    print(f"\n步骤:")
    print(f"  1. 访问: https://{network}.com/verifyContract")
    print(f"  2. 输入合约地址: {contract_address}")
    print(f"  3. 选择验证方式: Solidity (Standard Json Input)")
    print(f"  4. 编译器版本: {SOLC_VERSION}")
    print(f"  5. 勾选: Enabled optimization (200 runs)")
    print(f"  6. 勾选: Enabled via IR")
    print(f"  7. 上传 Standard Json Input 文件")
    print(f"  8. 填写构造函数参数（ABI-encoded）")
    print(f"  9. 提交验证\n")
    
    # 生成 Standard Json Input 文件
    print(f"📦 生成 Standard Json Input 文件...")
    generate_standard_json()
    
    return True


def generate_standard_json():
    """生成 BSCScan 验证需要的 Standard Json Input 文件"""
    try:
        with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
            source_code = f.read()
        
        standard_json = {
            "language": "Solidity",
            "sources": {
                "ModaMintToken.sol": {
                    "content": source_code
                }
            },
            "settings": {
                "evmVersion": "paris",
                "viaIR": True,
                "optimizer": {
                    "enabled": True,
                    "runs": 200
                },
                "outputSelection": {
                    "*": {
                        "*": [
                            "evm.bytecode",
                            "evm.deployedBytecode",
                            "abi",
                            "metadata"
                        ]
                    }
                }
            }
        }
        
        output_file = WORKSPACE / "bscscan_verify.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(standard_json, f, indent=2, ensure_ascii=False)
        
        print(f"  ✅ 已生成: {output_file}")
        print(f"     在 BSCScan 验证页面上传此文件")
        
    except Exception as e:
        print(f"  ❌ 生成失败: {e}")


def get_chain_name(chain_id):
    """获取链名称"""
    chains = {
        "1": "Ethereum 主网",
        "56": "BSC 主网",
        "97": "BSC 测试网",
        "137": "Polygon 主网",
        "42161": "Arbitrum One",
    }
    return chains.get(chain_id, f"未知链 ({chain_id})")


def main():
    print_header()
    
    # 获取合约地址
    contract_address = get_contract_address()
    
    if not contract_address.startswith("0x") or len(contract_address) != 42:
        print(f"\n❌ 无效的合约地址: {contract_address}")
        print(f"   地址应该是 0x 开头的 42 字符十六进制字符串")
        return
    
    print(f"\n✅ 合约地址: {contract_address}")
    print(f"✅ 链: {get_chain_name(CHAIN_ID)} (Chain ID: {CHAIN_ID})\n")
    
    # 方法1: Sourcify（完全免费，自动）
    success1 = verify_via_sourcify(contract_address, CHAIN_ID)
    
    # 方法2: OKLink（免费，手动）
    success2 = verify_via_oklink(contract_address, CHAIN_ID)
    
    # 方法3: BSCScan 手动（免费）
    success3 = verify_via_bscscan_manual(contract_address, CHAIN_ID)
    
    print(f"\n{'='*60}")
    print(f"  验证方法总结")
    print(f"{'='*60}")
    print(f"\n✅ 方法1: Sourcify - 完全免费，自动验证")
    print(f"   网址: https://sourcify.dev/#/verify/{CHAIN_ID}/{contract_address}")
    print(f"\n✅ 方法2: OKLink - 免费，手动上传")
    print(f"   网址: https://www.oklink.com/zh-hans/bsc/verify-contract-preliminary")
    print(f"\n✅ 方法3: BSCScan - 免费，手动上传")
    print(f"   网址: https://bscscan.com/verifyContract")
    print(f"\n💡 推荐: 优先使用方法1（Sourcify），最简单！")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
