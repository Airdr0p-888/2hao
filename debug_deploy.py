#!/usr/bin/env python3
"""
调试部署参数 - 检查哪些参数会导致构造函数 revert
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ========== 默认参数（从 launch.html 读取）==========
# 修改这些参数来测试
DEFAULT_PARAMS = {
    "name_": "Test Token",
    "symbol_": "TST",
    "totalSupply_": 1000000,  # 100万代币（不含18位小数）
    "mintCostBNB_": 2,  # 2 BNB（will be converted to wei）
    "fillBNB_": 20,  # 20 BNB 硬顶（will be converted to wei）
    "buyTax_": 500,  # 5% = 500 bps
    "sellTax_": 500,  # 5% = 500 bps
    "protectionBlocks_": 5,
    "marketingPct_": 2000,  # 20% = 2000 bps
    "burnPct_": 2000,  # 20%
    "dividendPct_": 2000,  # 20%
    "liquidityPct_": 4000,  # 40%
    "marketingWallet_": "0x1234567890123456789012345678901234567890",  # 替换为真实地址
    "dividendToken_": "0x0000000000000000000000000000000000000000",  # 通常为 0x0
    "owner_": "0x1234567890123456789012345678901234567890",  # 替换为真实地址
}

MAX_TAX = 2500  # 25%

def check_params(params):
    """检查参数是否满足构造函数的所有 require 条件"""
    errors = []
    warnings = []
    
    print(f"\n{'='*60}")
    print(f"  参数检查")
    print(f"{'='*60}\n")
    
    # 1. 检查税费
    buy_tax = params["buyTax_"]
    sell_tax = params["sellTax_"]
    
    print(f"[1/8] 买入税: {buy_tax} bps ({buy_tax/100}%)")
    if buy_tax > MAX_TAX:
        errors.append(f"❌ 买入税过高: {buy_tax} bps > {MAX_TAX} bps (MAX_TAX)")
    else:
        print(f"  ✅ 买入税正常 (<= {MAX_TAX} bps)")
    
    print(f"[2/8] 卖出税: {sell_tax} bps ({sell_tax/100}%)")
    if sell_tax > MAX_TAX:
        errors.append(f"❌ 卖出税过高: {sell_tax} bps > {MAX_TAX} bps (MAX_TAX)")
    else:
        print(f"  ✅ 卖出税正常 (<= {MAX_TAX} bps)")
    
    # 2. 检查税费分配总和 = 10000 bps
    marketing = params["marketingPct_"]
    burn = params["burnPct_"]
    dividend = params["dividendPct_"]
    liquidity = params["liquidityPct_"]
    total_pct = marketing + burn + dividend + liquidity
    
    print(f"\n[3/8] 税费分配:")
    print(f"  营销: {marketing} bps ({marketing/100}%)")
    print(f"  燃烧: {burn} bps ({burn/100}%)")
    print(f"  分红: {dividend} bps ({dividend/100}%)")
    print(f"  流动性: {liquidity} bps ({liquidity/100}%)")
    print(f"  总和: {total_pct} bps ({total_pct/100}%)")
    
    if total_pct != 10000:
        errors.append(f"❌ 税费分配总和 != 10000 bps: {total_pct}")
    else:
        print(f"  ✅ 税费分配总和 = 10000 bps (100%)")
    
    # 3. 检查 fillBNB_ > 0
    fill_bnb = params["fillBNB_"]
    print(f"\n[4/8] 预售硬顶 (fillBNB_): {fill_bnb} BNB")
    if fill_bnb <= 0:
        errors.append(f"❌ 预售硬顶必须 > 0")
    else:
        print(f"  ✅ 预售硬顶 > 0")
    
    # 4. 检查 mintCostBNB_ > 0
    mint_cost = params["mintCostBNB_"]
    print(f"\n[5/8] 单次 Mint 费用 (mintCostBNB_): {mint_cost} BNB")
    if mint_cost <= 0:
        errors.append(f"❌ Mint 费用必须 > 0")
    else:
        print(f"  ✅ Mint 费用 > 0")
    
    # 5. 检查 fillBNB_ >= mintCostBNB_
    print(f"\n[6/8] 硬顶 >= Mint 费用?")
    print(f"  fillBNB_ = {fill_bnb} BNB")
    print(f"  mintCostBNB_ = {mint_cost} BNB")
    if fill_bnb < mint_cost:
        errors.append(f"❌ 预售硬顶 < Mint 费用: {fill_bnb} < {mint_cost}")
    else:
        print(f"  ✅ 硬顶 >= Mint 费用")
    
    # 6. 检查 marketingWallet_ != address(0)
    marketing_wallet = params["marketingWallet_"]
    print(f"\n[7/8] 营销钱包: {marketing_wallet}")
    if marketing_wallet == "0x0000000000000000000000000000000000000000":
        errors.append(f"❌ 营销钱包地址为零地址")
    else:
        print(f"  ✅ 营销钱包地址有效")
    
    # 7. 检查 owner_ != address(0)
    owner = params["owner_"]
    print(f"\n[8/8] Owner: {owner}")
    if owner == "0x0000000000000000000000000000000000000000":
        errors.append(f"❌ Owner 地址为零地址")
    else:
        print(f"  ✅ Owner 地址有效")
    
    # 总结
    print(f"\n{'='*60}")
    if errors:
        print(f"  ❌ 发现 {len(errors)} 个错误:")
        for i, err in enumerate(errors):
            print(f"    {i+1}. {err}")
    else:
        print(f"  ✅ 所有参数检查通过！")
    print(f"{'='*60}\n")
    
    return len(errors) == 0


def main():
    print("="*60)
    print("  部署参数调试工具")
    print("="*60)
    
    # 使用默认参数检查
    print("\n当前参数:")
    for key, val in DEFAULT_PARAMS.items():
        print(f"  {key}: {val}")
    
    is_valid = check_params(DEFAULT_PARAMS)
    
    if not is_valid:
        print("\n💡 请修改 DEFAULT_PARAMS 中的参数，然后重新运行此脚本")
        print(f"   修改文件: {__file__}\n")
    else:
        print("\n✅ 参数全部有效，可以尝试部署！")
        print("\n⚠️ 注意：如果仍然部署失败，可能是:")
        print("  1. Uniswap V2 路由器地址错误")
        print("  2. 网络问题（测试网？主网？）")
        print("  3. 工厂合约地址错误")
        print("  4. 浏览器缓存了旧的 contract_data.js（请 Ctrl+Shift+R 强制刷新）\n")


if __name__ == "__main__":
    main()
