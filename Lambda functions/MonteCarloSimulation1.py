import json
import random
import boto3
import time

def lambda_handler(event, context):
    #This is called only during the warmup, returns without any computation
    if event.get('is_warmup'):
        return
    
    try:
        print(f"Received event: {event}")
        #Get all the data from the payload
        shots = int(event['d'])
        t = event['t']
        buy_list = event['buy_list']
        sell_list = event['sell_list']
        mean_list = event['mean_list']
        std_list = event['std_list']
        #The two lists to be returnedd
        var95_list = []
        var99_list = []
        #Set the target list to only execute the right one depening on the 't' received
        if t == 'buy':
            target_list = buy_list
        elif t == 'sell':
            target_list = sell_list
        else:
            return {
                'statusCode': 400,
                'body': json.dumps("Invalid transaction_type")
            }

        for index, signal in enumerate(target_list):
            if signal == 1:
                mean = float(mean_list[index])
                std_dev = float(std_list[index])
                simulated_returns = [random.gauss(mean, std_dev) for _ in range(shots)]
                simulated_returns.sort(reverse=True)
                var95 = simulated_returns[int(len(simulated_returns) * 0.05)]
                var99 = simulated_returns[int(len(simulated_returns) * 0.01)]
                var95_list.append(var95)
                var99_list.append(var99)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'var95_list': var95_list,
                'var99_list': var99_list
            })
        }
    except Exception as e:
        print(f"Errors: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Errors: {str(e)}")
        } 
