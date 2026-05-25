// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title DividendTracker
 * @notice 标准分红追踪合约（magnified per-share 机制）
 *          由主代币合约部署并拥有，负责分红会计和发放
 */

contract DividendTracker {
    address private _owner;
    address public dividendToken;

    uint256 private constant PRECISION = 1e12;

    // 分红会计
    uint256 private dividendsPerShare;
    mapping(address => int256)  private magnifiedDividendCorrections;
    mapping(address => uint256) private withdrawnDividends;

    // 持仓追踪（由主合约通过 setBalance 更新）
    uint256 private _totalSupply;
    uint256 public  minHoldForDividend;
    mapping(address => uint256) private _balanceOf;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event DividendClaimed(address indexed holder, uint256 amount);
    event DividendsDistributed(uint256 amount);
    event MinHoldUpdated(uint256 newMinHold);

    modifier onlyOwner() {
        require(_owner == msg.sender, "Tracker: not owner");
        _;
    }

    constructor() {
        _owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    function owner() public view returns (address) { return _owner; }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        emit OwnershipTransferred(_owner, newOwner);
        _owner = newOwner;
    }

    // 初始化（由主合约调用一次）
    function init(address token, uint256 minHold_) external onlyOwner {
        require(dividendToken == address(0), "Already init");
        dividendToken = token;
        minHoldForDividend = minHold_;
        emit MinHoldUpdated(minHold_);
    }

    function setDividendToken(address token) external onlyOwner {
        dividendToken = token;
    }

    function setMinHoldForDividend(uint256 amount) external onlyOwner {
        minHoldForDividend = amount;
        emit MinHoldUpdated(amount);
    }

    // 持仓同步（仅主合约可调用）
    function setBalance(address account, uint256 newBalance) external onlyOwner {
        uint256 oldBalance = _balanceOf[account];
        if (oldBalance == newBalance) return;

        if (newBalance > oldBalance) {
            _totalSupply += (newBalance - oldBalance);
        } else {
            _totalSupply -= (oldBalance - newBalance);
        }

        // 撤销旧余额贡献
        if (oldBalance > 0) {
            magnifiedDividendCorrections[account] -= int256(oldBalance) * int256(dividendsPerShare);
        }

        // 施加新余额贡献，减去已提取的分红修正
        if (newBalance > 0) {
            magnifiedDividendCorrections[account] += int256(newBalance) * int256(dividendsPerShare);
            magnifiedDividendCorrections[account] -= int256(withdrawnDividends[account]) * int256(PRECISION);
        } else {
            magnifiedDividendCorrections[account] = 0;
        }

        _balanceOf[account] = newBalance;
    }

    // 分红发放（仅主合约可调用）
    function distributeDividends(uint256 amount) external onlyOwner {
        if (amount == 0 || _totalSupply == 0) return;
        dividendsPerShare += (amount * PRECISION) / _totalSupply;
        emit DividendsDistributed(amount);
    }

    function totalSupply() public view returns (uint256) { return _totalSupply; }

    function balanceOf(address account) public view returns (uint256) { return _balanceOf[account]; }

    function getPendingDividend(address account) public view returns (uint256) {
        if (_balanceOf[account] == 0) return 0;
        if (_balanceOf[account] < minHoldForDividend) return 0;

        int256 mag = int256(_balanceOf[account]) * int256(dividendsPerShare)
                     + magnifiedDividendCorrections[account];
        if (mag <= 0) return 0;

        uint256 gross = uint256(mag) / PRECISION;
        if (gross <= withdrawnDividends[account]) return 0;
        return gross - withdrawnDividends[account];
    }

    function claim() external {
        uint256 pending = getPendingDividend(msg.sender);
        require(pending > 0, "Nothing to claim");

        withdrawnDividends[msg.sender] += pending;
        magnifiedDividendCorrections[msg.sender] -= int256(pending * PRECISION);

        (bool success, bytes memory data) = dividendToken.call(
            abi.encodeWithSignature("transfer(address,uint256)", msg.sender, pending)
        );
        require(success && (data.length == 0 || abi.decode(data, (bool))), "Transfer failed");

        emit DividendClaimed(msg.sender, pending);
    }

    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        (bool success, ) = token.call(
            abi.encodeWithSignature("transfer(address,uint256)", owner(), amount)
        );
        require(success);
    }

    receive() external payable {}
}
