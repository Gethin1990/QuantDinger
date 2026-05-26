#%%
"""Quick manual test: connect to TWS and fetch account summary."""

from app.services.ibkr_trading import IBKRClient, IBKRConfig
# config = IBKRConfig(host='127.0.0.1', port=7497, client_id=1, readonly=False, account='', timeout=20.0)
config = IBKRConfig(port=7497)
client = IBKRClient(config)

if not client.connect():
    print("Connection failed — is TWS/Gateway running?")
    raise SystemExit(1)

try:
    # summary = client.get_account_summary()
    # print(f"Account: {summary['account']}\n")
    # for tag, info in summary['summary'].items():
    #     print(f"  {tag:30s} {info['value']:>20s}  {info['currency']}")
    # 获取所有活跃委托单
    orders = client.get_open_orders()
    for order in orders:
        print(order)

    # 获取所有交易（包含委托单 + 状态）
    trades = client._ib.trades()  
    for trade in trades:
        print(trade)    
        
finally:
    client.disconnect()
    print("\nDisconnected.")


# %%
