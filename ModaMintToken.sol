// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./DividendTracker.sol";

/**
 * @title ModaMintToken
 * @notice BSC 链 Mint 代币 - 支持预售 Mint / 买卖税 / 税费分配 / 反机器人保护 / 独立分红追踪
 */

interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address recipient, uint256 amount) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function transferFrom(address sender, address recipient, uint256 amount) external returns (bool);
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
}

interface IUniswapV2Factory {
    function createPair(address tokenA, address tokenB) external returns (address pair);
}

interface IUniswapV2Router02 {
    function factory() external pure returns (address);
    function WETH() external pure returns (address);
    function swapExactTokensForETHSupportingFeeOnTransferTokens(
        uint amountIn, uint amountOutMin, address[] calldata path, address to, uint deadline
    ) external;
    function swapExactTokensForTokensSupportingFeeOnTransferTokens(
        uint amountIn, uint amountOutMin, address[] calldata path, address to, uint deadline
    ) external;
    function addLiquidityETH(
        address token, uint amountTokenDesired, uint amountTokenMin,
        uint amountETHMin, address to, uint deadline
    ) external payable returns (uint amountToken, uint amountETH, uint liquidity);
}

library SafeMath {
    function add(uint256 a, uint256 b) internal pure returns (uint256) { return a + b; }
    function sub(uint256 a, uint256 b) internal pure returns (uint256) { return a - b; }
    function mul(uint256 a, uint256 b) internal pure returns (uint256) { return a * b; }
    function div(uint256 a, uint256 b) internal pure returns (uint256) { return a / b; }
}

contract Ownable {
    address internal _owner;
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    constructor() { _owner = msg.sender; emit OwnershipTransferred(address(0), msg.sender); }
    function owner() public view virtual returns (address) { return _owner; }
    modifier onlyOwner() { require(owner() == msg.sender, "Ownable: caller is not owner"); _; }
    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "Ownable: zero address");
        emit OwnershipTransferred(_owner, newOwner);
        _owner = newOwner;
    }
    function renounceOwnership() public virtual onlyOwner {
        emit OwnershipTransferred(_owner, address(0));
        _owner = address(0);
    }
}

contract ModaMintToken is IERC20, Ownable {
    using SafeMath for uint256;

    string private _name;
    string private _symbol;
    uint8  private constant _decimals = 18;
    uint256 private _totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    // Mint 预售
    uint256 public mintCostBNB;
    uint256 public tokensPerMint;
    uint256 public fillAmountBNB;
    uint256 public totalBNBCollected;
    bool    public presaleActive;
    bool    public tradingActive;

    // 税费 (基点, 100 = 1%, 最大 1000 = 10%)
    uint256 public buyTaxBps;
    uint256 public sellTaxBps;

    // 税费分配 (总和=10000 bps)
    uint256 public marketingBps;
    uint256 public burnBps;
    uint256 public dividendBps;
    uint256 public liquidityBps;

    address public marketingWallet;
    address public dividendToken;

    // 反机器人
    uint256 public protectionEndBlock;

    // DEX
    IUniswapV2Router02 public immutable uniswapV2Router;
    address public immutable uniswapV2Pair;

    mapping(address => bool) public isExcludedFromTax;
    mapping(address => bool) public isExcludedFromProtection;
    mapping(address => uint256) private _lastTxBlock;

    // Mint 白名单
    bool    public whitelistMintOnly;
    mapping(address => bool) public isMintWhitelisted;

    // ===== 分红系统（由 DividendTracker 处理会计和发放）=====
    DividendTracker public dividendTracker;
    uint256 public pendingSwapForDividend;
    uint256 public pendingLiquidityTokens;
    uint256 public lastDividendBlock;
    uint256 public dividendCooldown;
    uint256 public dividendSwapThreshold;
    address private constant USDT_BSC = 0x55d398326f99059fF775485246999027B3197955;

    uint256 private constant MAX_TAX = 1000;

    event Minted(address indexed user, uint256 bnbAmount, uint256 tokenAmount);
    event PresaleCompleted(uint256 totalBNB, uint256 totalTokens);
    event TradingEnabled();
    event DividendProcessed(uint256 tokensSwapped, uint256 dividendReceived);
    event DividendClaimed(address indexed holder, address indexed dividendToken, uint256 amount);
    event MintWhitelistUpdated(address indexed account, bool whitelisted);
    event WhitelistMintToggled(bool active);

    uint256 public presaleTokenPct;

    constructor(
        string memory name_,
        string memory symbol_,
        uint256 totalSupply_,
        uint256 mintCostBNB_,
        uint256 fillBNB_,
        uint256 buyTax_,
        uint256 sellTax_,
        uint256 protectionBlocks_,
        uint256 marketingPct_,
        uint256 burnPct_,
        uint256 dividendPct_,
        uint256 liquidityPct_,
        address marketingWallet_,
        address dividendToken_,
        uint256 minHoldForDividend_,
        uint256 presaleTokenPct_,
        bool    whitelistMintOnly_,
        address owner_
    ) {
        require(buyTax_ <= MAX_TAX, "Buy tax too high");
        require(sellTax_ <= MAX_TAX, "Sell tax too high");
        require(marketingPct_ + burnPct_ + dividendPct_ + liquidityPct_ == 10000, "Tax alloc != 10000");
        require(fillBNB_ > 0, "Fill must > 0");
        require(mintCostBNB_ > 0, "Mint cost > 0");
        require(fillBNB_ >= mintCostBNB_, "Fill < mint cost");
        require(marketingWallet_ != address(0), "Wallet zero");
        require(owner_ != address(0), "Owner zero");
        require(presaleTokenPct_ >= 1 && presaleTokenPct_ <= 99, "Presale pct 1-99");

        _name = name_;
        _symbol = symbol_;
        _totalSupply = totalSupply_.mul(10 ** uint256(_decimals));

        emit OwnershipTransferred(address(0), msg.sender);
        emit OwnershipTransferred(msg.sender, owner_);
        _owner = owner_;

        dividendSwapThreshold = 100 * (10 ** uint256(_decimals));

        _balances[address(this)] = _totalSupply;
        mintCostBNB = mintCostBNB_;
        fillAmountBNB = fillBNB_;
        presaleTokenPct = presaleTokenPct_;

        uint256 presaleTokens = _totalSupply.mul(presaleTokenPct_).div(100);
        tokensPerMint = presaleTokens.mul(mintCostBNB_).div(fillBNB_);

        buyTaxBps = buyTax_;
        sellTaxBps = sellTax_;
        protectionEndBlock = block.number;
        marketingBps = marketingPct_;
        burnBps = burnPct_;
        dividendBps = dividendPct_;
        liquidityBps = liquidityPct_;
        marketingWallet = marketingWallet_;
        dividendToken = dividendToken_;
        dividendCooldown = 100;
        lastDividendBlock = block.number;
        whitelistMintOnly = whitelistMintOnly_;
        presaleActive = true;
        tradingActive = false;

        // 部署分红追踪合约
        dividendTracker = new DividendTracker();
        dividendTracker.init(dividendToken_ == address(0) ? USDT_BSC : dividendToken_, minHoldForDividend_);

        IUniswapV2Router02 _router = IUniswapV2Router02(0x10ED43C718714eb63d5aA57B78B54704E256024E);
        uniswapV2Router = _router;
        uniswapV2Pair = IUniswapV2Factory(_router.factory()).createPair(address(this), _router.WETH());

        isExcludedFromTax[address(this)] = true;
        isExcludedFromTax[owner_] = true;
        isExcludedFromTax[marketingWallet_] = true;
        isExcludedFromTax[address(_router)] = true;
        isExcludedFromProtection[address(_router)] = true;
        isExcludedFromProtection[address(this)] = true;
        isExcludedFromProtection[owner_] = true;

        emit Transfer(address(0), address(this), _totalSupply);
    }

    function name() public view returns (string memory) { return _name; }
    function symbol() public view returns (string memory) { return _symbol; }
    function decimals() public pure returns (uint8) { return _decimals; }
    function totalSupply() public view override returns (uint256) { return _totalSupply; }
    function balanceOf(address account) public view override returns (uint256) { return _balances[account]; }

    function transfer(address to, uint256 amount) public override returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function allowance(address _owner, address spender) public view override returns (uint256) {
        return _allowances[_owner][spender];
    }

    function approve(address spender, uint256 amount) public override returns (bool) {
        _approve(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        uint256 currentAllowance = _allowances[from][msg.sender];
        require(currentAllowance >= amount, "ERC20: exceed allowance");
        unchecked { _approve(from, msg.sender, currentAllowance - amount); }
        _transfer(from, to, amount);
        return true;
    }

    // ===== Mint 预售 =====
    function mint() external payable {
        _doMint(msg.sender, msg.value);
    }

    function _doMint(address user, uint256 bnbAmount) internal {
        require(presaleActive, "Presale ended");
        require(bnbAmount >= mintCostBNB, "Below min mint");
        require(totalBNBCollected.add(bnbAmount) <= fillAmountBNB, "Hardcap reached");
        if (whitelistMintOnly) {
            require(isMintWhitelisted[user], "Not in mint whitelist");
        }

        uint256 mintCount = bnbAmount.div(mintCostBNB);
        uint256 tokens = mintCount.mul(tokensPerMint);
        require(_balances[address(this)] >= tokens, "No tokens left");

        _balances[address(this)] = _balances[address(this)].sub(tokens);
        _balances[user] = _balances[user].add(tokens);
        totalBNBCollected = totalBNBCollected.add(bnbAmount);

        emit Minted(user, bnbAmount, tokens);
        emit Transfer(address(this), user, tokens);

        if (totalBNBCollected >= fillAmountBNB) {
            _completePresale();
        }
    }

    receive() external payable {
        if (presaleActive) {
            _doMint(msg.sender, msg.value);
        }
    }

    function completePresale() external onlyOwner {
        require(presaleActive, "Not active");
        _completePresale();
    }

    function _completePresale() internal {
        presaleActive = false;
        uint256 tokenBal = _balances[address(this)];
        uint256 bnbBal = address(this).balance;
        emit PresaleCompleted(bnbBal, tokenBal);

        if (tokenBal > 0 && bnbBal > 0) {
            _approve(address(this), address(uniswapV2Router), tokenBal);
            try uniswapV2Router.addLiquidityETH{value: bnbBal}(
                address(this), tokenBal, 0, 0, _owner, block.timestamp
            ) returns (uint, uint, uint) {
                tradingActive = true;
                emit TradingEnabled();
            } catch {
                // 底池添加失败，owner 可调用 addLiquidityManually() 手动补救
            }
        } else {
            tradingActive = true;
            emit TradingEnabled();
        }
    }

    function enableTrading() external onlyOwner {
        require(!tradingActive, "Already active");
        tradingActive = true;
        emit TradingEnabled();
    }

    // ===== 核心 _transfer =====
    function _transfer(address from, address to, uint256 amount) internal {
        require(from != address(0) && to != address(0), "Zero address");
        require(amount > 0, "Amount zero");
        require(_balances[from] >= amount, "Insufficient balance");

        bool isDexTransfer = (from == uniswapV2Pair || to == uniswapV2Pair);
        if (isDexTransfer && !tradingActive) {
            require(
                isExcludedFromTax[from] || isExcludedFromTax[to],
                "Trading not active"
            );
        }

        if (from != address(this)) {
            if (!isExcludedFromProtection[from] && !isExcludedFromProtection[to]) {
                require(block.number > protectionEndBlock, "Anti-bot active");
                require(_lastTxBlock[from] != block.number, "Same block");
            }
        }
        _lastTxBlock[from] = block.number;

        bool isBuy = (from == uniswapV2Pair && to != address(uniswapV2Router));
        bool isSell = (to == uniswapV2Pair && from != address(uniswapV2Router));
        uint256 taxAmount = 0;

        if (!isExcludedFromTax[from] && !isExcludedFromTax[to]) {
            if (isBuy) taxAmount = amount.mul(buyTaxBps).div(10000);
            else if (isSell) taxAmount = amount.mul(sellTaxBps).div(10000);
        }

        uint256 sendAmt = amount.sub(taxAmount);
        _balances[from] = _balances[from].sub(amount);
        _balances[to] = _balances[to].add(sendAmt);

        if (taxAmount > 0) {
            _balances[address(this)] = _balances[address(this)].add(taxAmount);
            _distributeTax(taxAmount, isSell);
        }

        emit Transfer(from, to, sendAmt);

        // 余额变更后再更新分红追踪（拿到正确的最新余额）
        if (dividendBps > 0) {
            dividendTracker.setBalance(from, _balances[from]);
            dividendTracker.setBalance(to, _balances[to]);
        }

        // 自动处理分红：买卖转账均可触发
        if (dividendSwapThreshold > 0 && pendingSwapForDividend >= dividendSwapThreshold) {
            if (block.number >= lastDividendBlock + dividendCooldown) {
                _processDividendSwap();
                lastDividendBlock = block.number;
            }
        }
    }

    function _distributeTax(uint256 taxAmt, bool isSell) internal {
        // 营销钱包
        uint256 mkt = taxAmt.mul(marketingBps).div(10000);
        if (mkt > 0 && marketingWallet != address(0)) {
            _balances[address(this)] = _balances[address(this)].sub(mkt);
            _balances[marketingWallet] = _balances[marketingWallet].add(mkt);
            emit Transfer(address(this), marketingWallet, mkt);
        }
        // 燃烧
        uint256 burn = taxAmt.mul(burnBps).div(10000);
        if (burn > 0) {
            _balances[address(this)] = _balances[address(this)].sub(burn);
            _totalSupply = _totalSupply.sub(burn);
            emit Transfer(address(this), address(0), burn);
        }
        // 流动性
        uint256 liq = taxAmt.mul(liquidityBps).div(10000);
        if (liq > 0) {
            pendingLiquidityTokens = pendingLiquidityTokens.add(liq);
        }
        // 分红
        if (dividendBps > 0) {
            uint256 divAmt = taxAmt.mul(dividendBps).div(10000);
            if (divAmt > 0) {
                pendingSwapForDividend = pendingSwapForDividend.add(divAmt);
            }
        }
    }

    // ===== Owner 函数 =====
    function setBuyTax(uint256 bps) external onlyOwner { require(bps <= MAX_TAX); buyTaxBps = bps; }
    function setSellTax(uint256 bps) external onlyOwner { require(bps <= MAX_TAX); sellTaxBps = bps; }
    function setMarketingWallet(address w) external onlyOwner { require(w != address(0)); marketingWallet = w; }
    function excludeFromTax(address a, bool ex) external onlyOwner { isExcludedFromTax[a] = ex; }
    function excludeFromProtection(address a, bool ex) external onlyOwner { isExcludedFromProtection[a] = ex; }
    function withdrawBNB() external onlyOwner { payable(owner()).transfer(address(this).balance); }

    function emergencyWithdrawToken(address token, uint256 amount) external onlyOwner {
        IERC20(token).transfer(owner(), amount);
    }

    function setMintWhitelist(address[] calldata accounts, bool whitelisted) external onlyOwner {
        for (uint256 i = 0; i < accounts.length; i++) {
            isMintWhitelisted[accounts[i]] = whitelisted;
            emit MintWhitelistUpdated(accounts[i], whitelisted);
        }
    }

    function setWhitelistMintOnly(bool active) external onlyOwner {
        whitelistMintOnly = active;
        emit WhitelistMintToggled(active);
    }

    function setProtectionEndBlock(uint256 blockNumber) external onlyOwner {
        protectionEndBlock = blockNumber;
    }

    function setTradingActive(bool active) external onlyOwner {
        tradingActive = active;
        if (active) emit TradingEnabled();
    }

    function setDividendSwapThreshold(uint256 amount) external onlyOwner {
        dividendSwapThreshold = amount;
    }

    function setDividendToken(address token) external onlyOwner {
        dividendToken = token;
        dividendTracker.setDividendToken(token == address(0) ? USDT_BSC : token);
    }

    function setMinHoldForDividend(uint256 amount) external onlyOwner {
        dividendTracker.setMinHoldForDividend(amount);
    }

    function setDividendCooldown(uint256 blocks) external onlyOwner {
        dividendCooldown = blocks;
    }

    function addLiquidityManually() external onlyOwner {
        uint256 t = _balances[address(this)];
        uint256 b = address(this).balance;
        require(t > 0 && b > 0, "Nothing to add");
        _approve(address(this), address(uniswapV2Router), t);
        uniswapV2Router.addLiquidityETH{value: b}(
            address(this), t, 0, 0, owner(), block.timestamp
        );
        presaleActive = false;
        if (!tradingActive) {
            tradingActive = true;
            emit TradingEnabled();
        }
    }

    // ===== 分红系统（swap 逻辑在主合约，会计在 tracker）=====

    /// @notice 获取当前生效的分红代币地址（留空默认 USDT）
    function getDividendToken() public view returns (address) {
        return dividendToken == address(0) ? USDT_BSC : dividendToken;
    }

    /// @notice 手动 swap 流动性累积代币 → BNB
    function processLiquidity() external {
        uint256 amount = pendingLiquidityTokens;
        require(amount > 0, "No pending liquidity");
        pendingLiquidityTokens = 0;

        address[] memory path = new address[](2);
        path[0] = address(this);
        path[1] = uniswapV2Router.WETH();
        _approve(address(this), address(uniswapV2Router), amount);
        try uniswapV2Router.swapExactTokensForETHSupportingFeeOnTransferTokens(
            amount, 0, path, address(this), block.timestamp
        ) {} catch {
            pendingLiquidityTokens = pendingLiquidityTokens.add(amount);
        }
    }

    /// @notice 手动触发分红处理（任何人可调用）
    function processDividend() external {
        require(pendingSwapForDividend > 0, "Nothing to process");
        _processDividendSwap();
    }

    /// @notice 查询地址的可领取分红数量（转发到 tracker）
    function getPendingDividend(address account) external view returns (uint256) {
        return dividendTracker.getPendingDividend(account);
    }

    /// @notice 持有者领取分红（转发到 tracker）
    function claimDividend() external {
        dividendTracker.claim();
    }

    /// @dev 内部：swap 积攒的代币 → 分红代币，发送给 tracker 并更新分配
    function _processDividendSwap() internal {
        uint256 amount = pendingSwapForDividend;
        if (amount == 0) return;
        pendingSwapForDividend = 0;

        address _divToken = getDividendToken();
        address weth = uniswapV2Router.WETH();

        uint256 balBefore = IERC20(_divToken).balanceOf(address(this));

        _approve(address(this), address(uniswapV2Router), amount);
        if (_divToken == weth) {
            address[] memory path = new address[](2);
            path[0] = address(this);
            path[1] = weth;
            try uniswapV2Router.swapExactTokensForTokensSupportingFeeOnTransferTokens(
                amount, 0, path, address(this), block.timestamp
            ) {} catch {
                pendingSwapForDividend = pendingSwapForDividend.add(amount);
                return;
            }
        } else {
            address[] memory path = new address[](3);
            path[0] = address(this);
            path[1] = weth;
            path[2] = _divToken;
            try uniswapV2Router.swapExactTokensForTokensSupportingFeeOnTransferTokens(
                amount, 0, path, address(this), block.timestamp
            ) {} catch {
                pendingSwapForDividend = pendingSwapForDividend.add(amount);
                return;
            }
        }

        uint256 received = IERC20(_divToken).balanceOf(address(this)).sub(balBefore);
        if (received > 0) {
            // 把分红代币发给 tracker
            IERC20(_divToken).transfer(address(dividendTracker), received);
            dividendTracker.distributeDividends(received);
            emit DividendProcessed(amount, received);
        }
    }

    function _approve(address _owner, address spender, uint256 amount) internal {
        require(_owner != address(0) && spender != address(0));
        _allowances[_owner][spender] = amount;
        emit Approval(_owner, spender, amount);
    }
}
