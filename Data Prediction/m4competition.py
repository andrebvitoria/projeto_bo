from numpy.random import seed
seed(42)
from tensorflow import set_random_seed
set_random_seed(42)

import tensorflow as tf
from sklearn.neural_network import MLPRegressor
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, SimpleRNN
from tensorflow.keras.optimizers import RMSprop as rmsprop
from tensorflow.keras import backend as ker
from math import sqrt
import numpy as np
import pandas as pd
import gc


def detrend(insample_data):
    """
    Calculates a & b parameters of LRL

    :param insample_data:
    :return:
    """
    x = np.arange(len(insample_data))
    a, b = np.polyfit(x, insample_data, 1)
    return a, b


def deseasonalize(original_ts, ppy):
    """
    Calculates and returns seasonal indices

    :param original_ts: original data
    :param ppy: periods per year
    :return:
    """
    """
    # === get in-sample data
    original_ts = original_ts[:-out_of_sample]
    """
    if seasonality_test(original_ts, ppy):
        # print("seasonal")
        # ==== get moving averages
        ma_ts = moving_averages(original_ts, ppy)

        # ==== get seasonality indices
        le_ts = original_ts * 100 / ma_ts
        le_ts = np.hstack((le_ts, np.full((ppy - (len(le_ts) % ppy)), np.nan)))
        le_ts = np.reshape(le_ts, (-1, ppy))
        si = np.nanmean(le_ts, 0)
        norm = np.sum(si) / (ppy * 100)
        si = si / norm
    else:
        # print("NOT seasonal")
        si = np.full(ppy, 100)

    return si


def moving_averages(ts_init, window):
    """
    Calculates the moving averages for a given TS

    :param ts_init: the original time series
    :param window: window length
    :return: moving averages ts
    """
    """
    As noted by Professor Isidro Lloret Galiana:
    line 82:
    if len(ts_init) % 2 == 0:

    should be changed to
    if window % 2 == 0:

    This change has a minor (less then 0.05%) impact on the calculations of the seasonal indices
    In order for the results to be fully replicable this change is not incorporated into the code below
    """

    if len(ts_init) % 2 == 0:
        ts_ma = np.reshape(pd.DataFrame(ts_init).rolling(window, center=True).mean().values, -1)
        # ts_ma = pd.rolling_mean(ts_init, window, center=True)
        ts_ma = np.reshape(pd.DataFrame(ts_ma).rolling(2, center=True).mean().values, -1)
        # ts_ma = pd.rolling_mean(ts_ma, 2, center=True)
        ts_ma = np.roll(ts_ma, -1)
    else:
        # ts_ma = pd.rolling_mean(ts_init, window, center=True)
        print(ts_init)
        ts_ma = np.reshape(pd.DataFrame(ts_init).rolling(window, center=True).mean().values, -1)

    return ts_ma


def seasonality_test(original_ts, ppy):
    """
    Seasonality test

    :param original_ts: time series
    :param ppy: periods per year
    :return: boolean value: whether the TS is seasonal
    """
    s = acf(original_ts, 1)
    for i in range(2, ppy):
        s = s + (acf(original_ts, i) ** 2)

    limit = 1.645 * (sqrt((1 + 2 * s) / len(original_ts)))

    return (abs(acf(original_ts, ppy))) > limit


def acf(data, k):
    """
    Autocorrelation function

    :param data: time series
    :param k: lag
    :return:
    """
    m = np.mean(data)
    s1 = 0
    for i in range(k, len(data)):
        s1 = s1 + ((data[i] - m) * (data[i - k] - m))

    s2 = 0
    for i in range(0, len(data)):
        s2 = s2 + ((data[i] - m) ** 2)

    return float(s1 / s2)


def split_into_train_test(data, in_num, fh):
    """
    Splits the series into train and test sets. Each step takes multiple points as inputs

    :param data: an individual TS
    :param fh: number of out of sample points
    :param in_num: number of input points for the forecast
    :return:
    """
    train, test = data[:-fh], data[-(fh + in_num):]
    x_train, y_train = train[:-1], np.roll(train, -in_num)[:-in_num]
    x_test, y_test = train[-in_num:], np.roll(test, -in_num)[:-in_num]

    # reshape input to be [samples, time steps, features] (N-NF samples, 1 time step, 1 feature)
    x_train = np.reshape(x_train, (-1, 1))
    x_test = np.reshape(x_test, (-1, 1))
    temp_test = np.roll(x_test, -1)
    temp_train = np.roll(x_train, -1)
    for x in range(1, in_num):
        x_train = np.concatenate((x_train[:-1], temp_train[:-1]), 1)
        x_test = np.concatenate((x_test[:-1], temp_test[:-1]), 1)
        temp_test = np.roll(temp_test, -1)[:-1]
        temp_train = np.roll(temp_train, -1)[:-1]

    return x_train, y_train, x_test, y_test


def rnn_bench(x_train, y_train, x_test, fh, input_size):
    """
    Forecasts using 6 SimpleRNN nodes in the hidden layer and a Dense output layer

    :param x_train: train data
    :param y_train: target values for training
    :param x_test: test data
    :param fh: forecasting horizon
    :param input_size: number of points used as input
    :return:
    """
    # reshape to match expected input
    x_train = np.reshape(x_train, (-1, input_size, 1))
    x_test = np.reshape(x_test, (-1, input_size, 1))

    # create the model
    model = Sequential([
        SimpleRNN(6, input_shape=(input_size, 1), activation='linear',
                  use_bias=False, kernel_initializer='glorot_uniform',
                  recurrent_initializer='orthogonal', bias_initializer='zeros',
                  dropout=0.0, recurrent_dropout=0.0),
        Dense(1, use_bias=True, activation='linear')
    ])
    opt = rmsprop(lr=0.001)
    model.compile(loss='mean_squared_error', optimizer=opt)

    # fit the model to the training data
    model.fit(x_train, y_train, epochs=100, batch_size=1)

    # make predictions
    y_hat_test = []
    last_prediction = model.predict(x_test)[0]
    for i in range(0, fh):
        y_hat_test.append(last_prediction)
        x_test[0] = np.roll(x_test[0], -1)
        x_test[0, (len(x_test[0]) - 1)] = last_prediction
        last_prediction = model.predict(x_test)[0]

    return np.asarray(y_hat_test)


def mlp_bench(x_train, y_train, x_test, fh):
    """
    Forecasts using a simple MLP which 6 nodes in the hidden layer

    :param x_train: train input data
    :param y_train: target values for training
    :param x_test: test data
    :param fh: forecasting horizon
    :return:
    """
    y_hat_test = []

    model = MLPRegressor(hidden_layer_sizes=6, activation='identity', solver='adam',
                         max_iter=100, learning_rate='adaptive', learning_rate_init=0.001,
                         random_state=42)
    model.fit(x_train, y_train)

    last_prediction = model.predict(x_test)[0]
    for i in range(0, fh):
        y_hat_test.append(last_prediction)
        x_test[0] = np.roll(x_test[0], -1)
        x_test[0, (len(x_test[0]) - 1)] = last_prediction
        last_prediction = model.predict(x_test)[0]

    return np.asarray(y_hat_test)


def smape(a, b):
    """
    Calculates sMAPE

    :param a: actual values
    :param b: predicted values
    :return: sMAPE
    """
    a = np.reshape(a, (-1,))
    b = np.reshape(b, (-1,))
    return np.mean(2.0 * np.abs(a - b) / (np.abs(a) + np.abs(b))).item()


def mase(insample, y_test, y_hat_test, freq):
    """
    Calculates MAsE

    :param insample: insample data
    :param y_test: out of sample target values
    :param y_hat_test: predicted values
    :param freq: data frequency
    :return:
    """
    y_hat_naive = []
    for i in range(freq, len(insample)):
        y_hat_naive.append(insample[(i - freq)])

    masep = np.mean(abs(insample[freq:] - y_hat_naive))

    return np.mean(abs(y_test - y_hat_test)) / masep


def m4_predict(data_all, in_size, freq, fh):
    data_all_prediction = list()
    
    err_sMAPE = []
    err_MASE = []
    
    counter = 0
    # ===== Main loop which goes through all timeseries =====
    for j in range(len(data_all)):
        ts = data_all[j]
    
        # remove seasonality
        seasonality_in = deseasonalize(ts, freq)
    
        for i in range(0, len(ts)):
            ts[i] = ts[i] * 100 / seasonality_in[i % freq]
    
        # detrending
        a, b = detrend(ts)
    
        for i in range(0, len(ts)):
            ts[i] = ts[i] - ((a * i) + b)
    
        x_train, y_train, x_test, y_test = split_into_train_test(ts, in_size, fh)
    
        # RNN benchmark - Produce forecasts
        y_hat_test = np.reshape(rnn_bench(x_train, y_train, x_test, fh, in_size), (-1))
    
    
        # add trend
        for i in range(0, len(ts)):
            ts[i] = ts[i] + ((a * i) + b)
    
        for i in range(0, fh):
            y_hat_test[i] = y_hat_test[i] + ((a * (len(ts) + i + 1)) + b)
    
        # add seasonality
        for i in range(0, len(ts)):
            ts[i] = ts[i] * seasonality_in[i % freq] / 100
    
        for i in range(len(ts), len(ts) + fh):
            y_hat_test[i - len(ts)] = y_hat_test[i - len(ts)] * seasonality_in[i % freq] / 100
    
        # check if negative or extreme
        for i in range(len(y_hat_test)):
            if y_hat_test[i] < 0:
                y_hat_test[i] = 0
    
            if y_hat_test[i] > (1000 * max(ts)):
                y_hat_test[i] = max(ts)
        
        data_all_prediction.append(y_hat_test)
        
        x_train, y_train, x_test, y_test = split_into_train_test(ts, in_size, fh)
    
        # Calculate errors
        err_sMAPE.append(smape(y_test, y_hat_test))
        err_MASE.append(mase(ts[:-fh], y_test, y_hat_test, freq))
    
        # memory handling
        ker.clear_session()
        tf.reset_default_graph()
        gc.collect()
    
        counter = counter + 1
        print("-------------TS ID: ", counter, "-------------")
    
    print("\n\n---------FINAL RESULTS---------")
    print("=============sMAPE=============\n")
    print("#### RNN ####\n", np.mean(err_sMAPE), "\n")
    print("==============MASE=============")
    print("#### RNN ####\n", np.mean(err_MASE), "\n")
    
    return np.array(data_all_prediction), err_sMAPE, err_MASE
