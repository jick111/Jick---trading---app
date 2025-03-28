import asyncio
import json
import websockets
import random
from flask import Flask, render_template, request, jsonify

# Initialize Flask app
app = Flask(__name__)

# Default values
API_TOKEN = "TbFSXhorXzUohZR"
SYMBOL = "R_100"
STAKE_AMOUNT = 1000
DURATION = 1
DURATION_UNIT = "t"
CONTRACT_TYPE = "DIGITDIFF"
account_balance = 0  # This will hold the real account balance
profit_loss = 0  # Tracks overall profit/loss
barrier_digit = '9'  # Default, will be updated dynamically
is_trading = False  # To track whether the bot is running


async def get_account_balance():
    """Fetch real account balance from Deriv API"""
    global account_balance
    async with websockets.connect("wss://ws.binaryws.com/websockets/v3?app_id=70489") as websocket:
        await websocket.send(json.dumps({"authorize": API_TOKEN}))
        auth_response = json.loads(await websocket.recv())

        if "error" in auth_response:
            print("Authorization Failed:", auth_response["error"]["message"])
            return

        await websocket.send(json.dumps({"balance": 1}))
        balance_response = json.loads(await websocket.recv())

        if "error" in balance_response:
            print("Balance fetch failed:", balance_response["error"]["message"])
        else:
            account_balance = balance_response["balance"]["balance"]
            print(f"Account Balance: ${account_balance}")


@app.route('/')
async def home():
    await get_account_balance()
    return render_template('index.html', api_token=API_TOKEN, symbol=SYMBOL,
                           stake_amount=STAKE_AMOUNT, duration=DURATION,
                           account_balance=account_balance, profit_loss=profit_loss,
                           is_trading=is_trading)


@app.route('/get_status')
def get_status():
    """Returns the updated balance and profit/loss to the frontend"""
    return jsonify({
        "account_balance": account_balance,
        "profit_loss": profit_loss,
        "is_trading": is_trading
    })


@app.route('/start_trading', methods=['POST'])
def start_trading():
    global is_trading
    is_trading = True
    asyncio.run(trade_digitdiff())
    return jsonify({"status": "success", "message": "Trading started!"})


@app.route('/stop_trading', methods=['POST'])
def stop_trading():
    global is_trading
    is_trading = False
    return jsonify({"status": "success", "message": "Trading stopped!"})


@app.route('/update_settings', methods=['POST'])
def update_settings():
    global API_TOKEN, SYMBOL, STAKE_AMOUNT, DURATION, DURATION_UNIT, CONTRACT_TYPE
    API_TOKEN = request.form['api_token']
    SYMBOL = request.form['symbol']
    STAKE_AMOUNT = int(request.form['stake_amount'])
    DURATION = int(request.form['duration'])
    DURATION_UNIT = request.form['duration_unit']
    CONTRACT_TYPE = request.form['contract_type']
    return jsonify({"status": "success", "message": "Settings updated!"})


async def trade_digitdiff():
    global account_balance, profit_loss, barrier_digit, is_trading
    async with websockets.connect("wss://ws.binaryws.com/websockets/v3?app_id=70489") as websocket:
        await websocket.send(json.dumps({"authorize": API_TOKEN}))
        auth_response = json.loads(await websocket.recv())

        if "error" in auth_response:
            print("Authorization Failed:", auth_response["error"]["message"])
            return

        print("Authorized Successfully!")

        while is_trading:
            barrier_digit = str(random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8]))  # Exclude 9
            print(f"Trading with barrier: {barrier_digit} and stake: {STAKE_AMOUNT}")

            trade_request = {
                "buy": 1,
                "parameters": {
                    "amount": STAKE_AMOUNT,
                    "app_markup_percentage": "0",
                    "barrier": barrier_digit,
                    "basis": "stake",
                    "contract_type": CONTRACT_TYPE,
                    "currency": "USD",
                    "duration": DURATION,
                    "duration_unit": DURATION_UNIT,
                    "symbol": SYMBOL
                },
                "price": STAKE_AMOUNT
            }

            await websocket.send(json.dumps(trade_request))
            response = json.loads(await websocket.recv())

            if "error" in response:
                print(f"Trade failed for barrier {barrier_digit}: {response['error']['message']}")
            else:
                contract_id = response['buy']['contract_id']
                print(f"Trade placed with barrier {barrier_digit}: Contract ID: {contract_id}")

                await websocket.send(json.dumps({"proposal_open_contract": 1, "contract_id": contract_id}))
                result = json.loads(await websocket.recv())

                if "error" in result:
                    print(f"Error fetching contract result: {result['error']['message']}")
                else:
                    contract = result.get("proposal_open_contract", {})
                    if contract.get("is_sold", False):
                        profit = contract.get("profit", 0)
                        exit_digit = str(contract.get("exit_tick", "")[-1])

                        if exit_digit != barrier_digit:
                            print(f"✅ Win! Exit spot: {exit_digit} was different from barrier {barrier_digit}. Profit: {profit}")
                            account_balance += profit  # Update balance
                            profit_loss += profit  # Track profit
                        else:
                            print(f"❌ Loss! Exit spot: {exit_digit} matched barrier {barrier_digit}. Loss: {profit}")
                            account_balance += profit  # Losses are negative, so this still works
                            profit_loss += profit  # Track loss

            await asyncio.sleep(0.1)
