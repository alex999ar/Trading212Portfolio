import re
from forex_python.converter import CurrencyRates
from bs4 import BeautifulSoup as bs
import requests
from yahoo_fin import stock_info as si
import pandas as pd
from usefulFunctions import split_text

def makeStats(dfMail, USER_CURRENCY): 
    pd.set_option("display.max_rows", None, "display.max_columns", None)

    #initialise the dataframes
    dfOrder = pd.DataFrame()

    #if there is an offset.csv get the data
    try:
        dfOrder = pd.read_csv("orders.csv")

        #drop useless columns
        dfOrder = dfOrder.drop(columns=['Name', 'Price / share', 'Currency (Price / share)', 'Exchange rate'])

        #split columns like in the email
        dfOrder[['Date','Time']] = dfOrder.Time.str.split(" ",expand=True)
        dfOrder[['Order Type','Direction']] = dfOrder.Action.str.split(" ",expand=True)

        #re-arrange the columns
        dfOrder = dfOrder.reindex(['Date', 'Time', 'ID', 'Ticker','ISIN', 'Order Type', 'Direction', 'No. of shares', 
                                     'Total ('+USER_CURRENCY+')', 'Finra fee ('+USER_CURRENCY+')', 'Stamp duty reserve tax ('+USER_CURRENCY+')'], axis=1)

        #rename the columns
        dfOrder = dfOrder.rename(columns={"No. of shares": "Quantity", 'Total ('+USER_CURRENCY+')': "Total", 'Finra fee ('+USER_CURRENCY+')': 'Commission', 
                                            'Stamp duty reserve tax ('+USER_CURRENCY+')' : 'Charges and Fees', 'ID' : 'Id'})
        #capitalise Buy and Sell
        dfOrder['Direction'] = dfOrder['Direction'].str.capitalize()


        print("-----------------------------------------------Order Data-----------------------------------------------")
        print(dfOrder)
    except:
        #do nothing
        print("There is no orders csv")


 
    #if there are email data get them
    if not dfMail.empty:
        print("-----------------------------------------------Mail Data-----------------------------------------------")
        print(dfMail)
    else:
        print("No email Data")

    #combine all the data in one dataframe
    if((not dfOrder.empty) and (not dfMail.empty)):
        dfPortfolio = pd.concat([dfMail, dfOrder], axis=0, join='outer')
    elif(not dfOrder.empty):
        dfPortfolio = dfOrder
    elif(not dfMail.empty):
        dfPortfolio = dfMail
    else:
        #if you don't have any data return an empty dataFrame
        return pd.DataFrame()
    print("-----------------------------------------------Portfolio Data-----------------------------------------------")
    print(dfPortfolio)


    #initialise the titles for the stats arrays
    formattedPortfolio = [["Ticker", "ISIN", "Quantity", "Invested", "Average Price", "Withdrew", "LastClosedProfit", "Current Fees", "Total Fees"]]
    
    #group all the rows with same stock name

    groupTicker = dfPortfolio.groupby("Ticker")


    for ticker, group in groupTicker: 
        #stock is the name of the stock
        #we get isin from the grouped stocks
        isin = group["ISIN"].head(1).to_string(index=False).strip()

        #initialise variables 
        quantity = 0
        invested = 0
        withdrew = 0
        fees = 0
        totalFees = 0
        lastClosedProfit = 0

        #calculate their actual value by looping through the rows
        for _, row in group.iterrows():
            if row["Direction"] == "Buy":
                quantity += row["Quantity"]
                invested += row["Total"]

                #Fees (this is to check that it has a number -> it isn't NaN)
                if row["Commission"] == row["Commission"]:
                    fees += row["Commission"]
                if row["Charges and Fees"] == row["Charges and Fees"]:
                    fees += row["Charges and Fees"]

            else:
                quantity -= row["Quantity"]
                withdrew += row["Total"]

                #Fees (this is to check that it has a number -> it isn't NaN)
                if row["Commission"] == row["Commission"]:
                    fees += row["Commission"]
                if row["Charges and Fees"] == row["Charges and Fees"]:
                    fees += row["Charges and Fees"]
            
            #when quantity becomes == 0 then this position has beeen closed 
            if quantity == 0:
                #update last closed profit and reset everything else
                lastClosedProfit += withdrew - invested - fees
                invested = 0
                withdrew = 0
                fees = 0
                #totalFees variable tracks all th payed fees while the fees variable tracks the fees since
                #the last time the position was closed
                totalFees += fees

        #calculate current average Price (quantity must be >0)
        if quantity > 0:
            averagePrice = (invested + fees - withdrew)/ quantity
            averagePrice = round(averagePrice, 3)
        else:
            averagePrice =  float('nan')

        #add to the total fees the current fees
        totalFees += fees

        #remove fractions of a cent caused by the way computers store values
        invested = round(invested, 3)
        withdrew = round(withdrew, 3)
        lastClosedProfit = round(lastClosedProfit, 3)
        fees = round(fees, 4)
        totalFees = round(totalFees, 4)
        
        #add all the data to an array
        formattedPortfolio.append([ticker, isin, quantity, invested, averagePrice, withdrew, lastClosedProfit, fees, totalFees])

    dfFormattedPortfolio = pd.DataFrame(data = formattedPortfolio[1:][0:],       # values
                                        columns = formattedPortfolio[0][0:])     # 1st row as the column names
    #drop rows where quantity == 0
    dfFormattedPortfolio = dfFormattedPortfolio[dfFormattedPortfolio["Quantity"] != 0]
    #reset the index
    dfFormattedPortfolio.reset_index(drop=True, inplace=True)

    #get the real stock names
    stocks = dfFormattedPortfolio["Ticker"].tolist()
    isins = dfFormattedPortfolio["ISIN"].tolist()
    for i in range(len(stocks)):
        #first try in the london stock exchange (because Trading212 uses primarily this exchange)
        try:
            si.get_live_price(stocks[i]+".L")
            stocks[i] = stocks[i]+".L"
        except:
            #if it fails try with the normal name
            try:                
                si.get_live_price(stocks[i])
            #if this also fails take the first stock name that matches the isin
            except:
                try:
                    #search in yahoo finance with the isin
                    url = "https://query2.finance.yahoo.com/v1/finance/search"
                    params = {'q': isins[i], 'quotesCount': 1, 'newsCount': 0}
                    r = requests.get(url, params=params)
                    #get all the data for this isin
                    data = r.json()
                    #get the stock symbol for this isin
                    symbol = data['quotes'][0]['symbol']
                    stocks[i] = symbol
                    si.get_live_price(stocks[i])
                except:
                    print("This ticker couldn't be found in any stock exchange")
                    stocks[i] = "NaN"

    dfFormattedPortfolio["Ticker"] = pd.DataFrame(stocks)

    #drop rows where Ticker == "NaN"
    dfFormattedPortfolio = dfFormattedPortfolio[dfFormattedPortfolio["Ticker"] != "NaN"]
    #reset the index
    dfFormattedPortfolio.reset_index(drop=True, inplace=True)
    dfFormattedPortfolio["Ticker"] = pd.DataFrame(stocks)


    print("-----------------------------------------------Formated Portfolio Data-----------------------------------------------")
    print(dfFormattedPortfolio)
    return dfFormattedPortfolio

def yahooInfo(dfFormattedPortfolio, USER_CURRENCY):
    #get all the stock names
    stocks = dfFormattedPortfolio["Ticker"].tolist()
    #get all the isin
    isins = dfFormattedPortfolio["ISIN"].tolist()
    #get the number of share we have
    shares = (dfFormattedPortfolio["Quantity"]).tolist()

    #get the rates
    c = CurrencyRates()
    if USER_CURRENCY != "USD":
        usdToUserCurrencyRate = c.get_rate('USD', USER_CURRENCY)
    if USER_CURRENCY != "EUR":
        euroToUserCurrencyRate = c.get_rate('EUR', USER_CURRENCY)
    if USER_CURRENCY != "GBP":
        gbpToUserCurrencyRate = c.get_rate('GBP', USER_CURRENCY)
    if USER_CURRENCY != "NOK":
        nokToUserCurrencyRate = c.get_rate('NOK', USER_CURRENCY)                   


    #the list where all the stocks values (in the users currency) will be saved
    userCurrencyVal = []

    #get the current value of each stock
    print("Getting the current value of each stock")
    for i in range(len(stocks)):
        try:
            #get the current value of the stock in whatever currency
            curPrice = si.get_live_price(stocks[i]) * shares[i] 
           
            #get the currency the stock is traded in by going to that url
            url = "https://finance.yahoo.com/quote/"
            #get the html page of the stock
            r = requests.get(str(url+stocks[i]))
            #get the html text
            soup = bs(r.text, "lxml")
            #find the div which contains the words "Currency in" and get the text
            currencyInfo = soup.find("div", string=re.compile("Currency in"))
            #get the currency (the word after the words "Currency in")
            stockCurrency = str(split_text(currencyInfo.text, "Currency in", ""))
            
            #convert everything to user's currency
            #if its the same currency with the user no need to do anything
            if stockCurrency == USER_CURRENCY:
                curPrice = curPrice
            #check if USER_CURRENCY == GBP but stockCurrency == GBp to move the decimals
            elif stockCurrency == "GBp" and USER_CURRENCY == "GBP":
                curPrice *= 0.01
            #change the currency if it is different
            elif stockCurrency == "USD":
                curPrice = usdToUserCurrencyRate*curPrice
            elif stockCurrency == "GBp":
                curPrice = gbpToUserCurrencyRate*curPrice*0.01
            elif stockCurrency == "NOK":
                curPrice = nokToUserCurrencyRate*curPrice
            else:
                print("Trying to get the currency rate for " + stockCurrency)
                try:
                    tempRate = c.get_rate(stockCurrency, USER_CURRENCY)
                    curPrice = tempRate * curPrice
                except:
                    print("could not get the currency rate for " + stockCurrency)
                    curPrice = float("NaN")

            #append the value in the correct currency
            userCurrencyVal.append(round(curPrice,2))
            
        #if the stock name doesn't exist in yahoo finance print error message
        except Exception as e:
            print("This exception should never occur something is terribly wrong")
            print(e)
            userCurrencyVal.append(float("NaN"))

    #get the value we have currently invested
    investedValue= (dfFormattedPortfolio["Invested"] - dfFormattedPortfolio["Withdrew"]).tolist()

    #this where we will store the temporary profit/loss
    tempProfit = [float("nan")] * len(isins)

    #remove from current value the total value currently invested
    for i in range(len(isins)):
        if userCurrencyVal[i] == userCurrencyVal[i]:
            tempProfit[i] = userCurrencyVal[i] - investedValue[i]
    
    #append everything in this array
    liveStockData = [["Stock", "ISIN", "Quantity", "Average Price", "Invested Value", "Current Investment Value", "Profit"]]

    quantity = dfFormattedPortfolio["Quantity"].tolist()
    averagePrice = dfFormattedPortfolio["Average Price"].tolist()

    for i in range(len(stocks)):
        liveStockData.append([stocks[i], isins[i], quantity[i], averagePrice[i], investedValue[i], userCurrencyVal[i], tempProfit[i]])    

    print("-----------------------------------------------Current Positions' Value-----------------------------------------------")

    dfLivePositionValues = pd.DataFrame(data = liveStockData[1:][0:],       # values
                                        columns = liveStockData[0][0:])     # 1st row as the column names
    print(dfLivePositionValues)
    return dfLivePositionValues
