import solcx, json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SOLC_VERSION = '0.8.20'
OPTIMIZE_RUNS = 200
EVM_VERSION = 'paris'

def main():
    with open('ModaMintToken.sol', 'r', encoding='utf-8') as f:
        src = f.read()

    print(f'ModaMintToken.sol length: {len(src)}')
    print(f'Has DividendTracker import: {"DividendTracker" in src}')

    # 用 viaIR=True 绕过 Stack Too Deep（构造函数参数多）
    print(f'\nCompiling with solc {SOLC_VERSION}, viaIR=True...')
    result = solcx.compile_source(
        src,
        solc_version=SOLC_VERSION,
        via_ir=True,
        optimize=True,
        optimize_runs=OPTIMIZE_RUNS,
        evm_version=EVM_VERSION,
        output_values=['abi', 'bin']
    )

    # 只处理 ModaMintToken 主合约（接口没有 bin）
    target = None
    for key in result:
        if 'ModaMintToken' in key and 'I' not in key.split(':')[-1]:
            target = key
            break

    if not target:
        print('ERROR: ModaMintToken contract not found in result!')
        print('Available keys:', list(result.keys()))
        return

    abi = result[target]['abi']
    bin = result[target]['bin']
    print(f'\n✅ Found contract: {target}')
    print(f'  ABI entries: {len(abi)}')
    print(f'  Bytecode length: {len(bin)} hex chars ({len(bin)//2} bytes)')

    # 写入 contract_data.js（供 launch.html 部署用）
    with open('contract_data.js', 'w', encoding='utf-8') as f:
        f.write(f'const modamint_abi = {json.dumps(abi, indent=2)};\n')
        f.write(f'const modamint_bytecode = "0x{bin}";\n')
    print(f'  → Saved to contract_data.js')

    # 写入纯 bytecode（供 BSCScan 验证用）
    with open('ModaMintToken_bytecode.txt', 'w', encoding='utf-8') as f:
        f.write(bin)
    print(f'  → Bytecode saved to ModaMintToken_bytecode.txt')

    print('\n✅ Compile finished.')

if __name__ == '__main__':
    main()
