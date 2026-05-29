# SatMiner - BSC PoW Mining Client

SatMiner is a high-performance desktop GUI application designed for mining the **Satoshi (SAT)** token on the Binance Smart Chain (BSC). It utilizes Proof-of-Work (PoW) to secure the network and reward miners.

## 🚀 Key Features
- **High Performance**: Multi-process mining engine that bypasses Python's GIL for maximum hashing power.
- **User-Friendly Interface**: Modern dark-themed GUI inspired by classic Bitcoin wallets.
- **Real-time Monitoring**: Track your hashrate, block rewards, and mining history in real-time.
- **Wallet Integration**: Direct balance checks for BNB and SAT tokens.
- **Customizable Settings**: Adjustable RPC endpoints, gas prices, and gas limits.

## 📋 Contract Information
- **Contract Address**: `0x14Dc4b4929c664534f1d4D64107d8F36CbF906a0`
- **Network**: Binance Smart Chain (BSC)
- **Token Symbol**: SAT
- **Decimals**: 8
- **Total Supply**: 21,000,000 SAT
- **Mining Reward**: 50 SAT (halving every era)

---

## 🛠️ Installation Guide

### Option 1: Run from Source (Recommended for Developers)
1. **Install Python**: Ensure you have Python 3.10 or newer installed. [Download Python](https://www.python.org/downloads/)
2. **Clone the Repository**:
   ```bash
   git clone https://github.com/SatCoinBSC/SatMiner.git
   cd SatMiner
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Launch the Miner**:
   ```bash
   python satoshi_miner.py
   ```

### Option 2: Build Executable (Windows)
1. Download the source code and extract it.
2. Double-click the `build.bat` file.
3. Once completed, find `SatoshiMiner.exe` in the `dist/` folder.

---

## ⛏️ How to Mine

1. **Configure RPC**: Use the default BSC RPC or enter your own private node URL for better stability.
2. **Connect Wallet**: Enter your BSC wallet's **Private Key**. 
   - *Note: Your private key is only used locally to sign mining transactions and is never stored on disk or transmitted to any server.*
3. **Set Gas**: Adjust the Gas Price (Gwei) based on current network congestion. 5 Gwei is usually sufficient for BSC.
4. **Start Mining**: Click the **"Start Mining"** button. The engine will begin searching for valid nonces.
5. **Auto-Submission**: When a valid block is found, the miner will automatically submit the transaction to the BSC network.

---

## ⚠️ Requirements & Safety
- **Gas Fees**: You must have a small amount of **BNB** in your wallet to pay for transaction fees when a block is found.
- **Hardware**: Mining is CPU-intensive. Ensure your cooling system is working properly.
- **Security**: Never share your private key with anyone. This software only uses it locally for signing.

## 📄 License
This project is released under the MIT License.
