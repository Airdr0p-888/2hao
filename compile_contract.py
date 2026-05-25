"""
编译 ModaMintToken.sol 并更新 contract_data.js
编译设置：solc 0.8.20 + via-IR + optimizer 200 runs + EVM paris
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
import solcx
import json
import re
import os

SOL_VERSION = "0.8.20"
CONTRACT_FILE = os.path.join(os.path.dirname(__file__), "ModaMintToken.sol")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "contract_data.js")

def compile_contract():
    print(f"[1/3] 读取源代码: {CONTRACT_FILE}")
    with open(CONTRACT_FILE, "r", encoding="utf-8") as f:
        source_code = f.read()
    
    print(f"[2/3] 编译合约 (solc {SOL_VERSION}, via-IR, optimizer 200 runs, EVM paris)...")
    
    # 使用 Standard JSON Input 格式（支持 via-IR）
    standard_json_input = {
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
                        "evm.bytecode.object",
                        "evm.bytecode.sourceMap",
                        "evm.deployedBytecode.object",
                        "evm.deployedBytecode.sourceMap",
                        "abi",
                        "metadata",
                        "devdoc",
                        "userdoc",
                        "storageLayout",
                        "evm.legacyAssembly",
                        "evm.assembly"
                    ]
                }
            }
        }
    }
    
    # 编译
    result = solcx.compile_standard(
        standard_json_input,
        solc_version=SOL_VERSION,
        allow_paths="."
    )
    
    # 检查错误
    if "errors" in result:
        errors = result["errors"]
        fatal_errors = [e for e in errors if e.get("severity") == "error"]
        if fatal_errors:
            print(f"❌ 编译失败！")
            for e in fatal_errors:
                print(f"  错误: {e.get('formattedMessage', e.get('message', ''))}")
            return False
        # 只是警告，继续
        warnings = [e for e in errors if e.get("severity") == "warning"]
        if warnings:
            print(f"⚠️ {len(warnings)} 个警告（不影响）")
    
    # 提取 bytecode、ABI 和 metadata
    contract_output = result["contracts"]["ModaMintToken.sol"]["ModaMintToken"]
    
    bytecode = contract_output["evm"]["bytecode"]["object"]
    abi = contract_output["abi"]
    metadata = result.get("contracts", {}).get("ModaMintToken.sol", {}).get("ModaMintToken", {}).get("metadata", "")
    
    # 也尝试从顶层获取 metadata
    if not metadata and "sources" in result:
        # metadata 可能在其他地方
        pass
    
    print(f"  ✅ 编译成功！")
    print(f"  Bytecode 长度: {len(bytecode)} 字符")
    print(f"  ABI 函数数量: {len(abi)}")
    if metadata:
        print(f"  ✅ Metadata 已生成")
    
    # 检查 CBOR metadata 是否存在（bytecode 末尾的 a264...）
    if "a264" in bytecode[-200:]:
        print(f"  ✅ CBOR metadata 已包含在 bytecode 末尾")
    else:
        print(f"  ⚠️ 注意：bytecode 末尾未检测到 CBOR metadata")
    
    # 生成 contract_data.js
    print(f"[3/3] 生成 {OUTPUT_FILE}...")
    
    abi_json = json.dumps(abi, separators=(',', ':'))
    
    # bytecode 必须带 0x 前缀（launch.html 依赖此格式提取构造函数参数）
    if not bytecode.startswith('0x'):
        bytecode = '0x' + bytecode
    
    js_content = f"const CONTRACT_ABI = {abi_json};\n"
    js_content += f"const CONTRACT_BYTECODE = \"{bytecode}\";\n"
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(js_content)
    
    print(f"  ✅ {OUTPUT_FILE} 已更新！")
    
    # 保存 metadata.json（Sourcify 验证必需）
    metadata_file = os.path.join(os.path.dirname(__file__), "metadata.json")
    try:
        # 从 compilation result 获取 metadata
        # metadata 在 result["contracts"]["ModaMintToken.sol"]["ModaMintToken"]["metadata"]
        metadata_str = result["contracts"]["ModaMintToken.sol"]["ModaMintToken"].get("metadata", "")
        if metadata_str:
            with open(metadata_file, "w", encoding="utf-8") as f:
                f.write(metadata_str)
            print(f"  ✅ metadata.json 已保存（Sourcify 验证必需）")
        else:
            # 尝试从 standard json output 获取
            print(f"  ⚠️ 未找到 metadata，尝试从编译输出提取...")
    except Exception as e:
        print(f"  ⚠️ 保存 metadata.json 失败: {e}")
    
    # 同时输出构造函数参数信息（方便验证）
    ctor_abi = [item for item in abi if item.get("type") == "constructor"]
    if ctor_abi:
        inputs = ctor_abi[0].get("inputs", [])
        print(f"\n📋 构造函数参数 ({len(inputs)} 个):")
        for i, inp in enumerate(inputs):
            print(f"  [{i}] {inp['type']} {inp['name']}")
    
    return True

if __name__ == "__main__":
    success = compile_contract()
    if success:
        print("\n✅ 全部完成！contract_data.js 已更新。")
        print("   现在可以在 BSCScan 上验证合约了。")
    else:
        print("\n❌ 编译失败，请检查错误信息。")
