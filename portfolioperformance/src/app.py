from datetime import date
from io import StringIO
from typing import *
from urllib import parse

import pandas as pd
import numpy as np

from .model import Model

'''
    @brief Entry point for the application
'''

class App:
    '''
        Initialize the app with the following parameters:

        @param path: path to the data file
        @param gammas: risk averse levels
        @param timeHorizon: time horizons for rolling window
        @param models: list of models to run
        @param dateRange: date range for the data file, default is [], which means no date range
        @param delim: delimiter for the data file, default is ",", other option is "\s+" for spaces and tabs
        @param date: whether the data file has a date column, as the first column, default is False
        @param riskFactorPos: list of positions of the risk factors in the data file, default is None, start at pos 1, excluding date column
        @param riskFreePos: position of the risk-free asset in the data file, default is 1, start at pos 1, excluding date column

        @return: App object
    '''

    def __init__(self, path: str,
                gammas: list[int],
                timeHorizon: list[int],
                models: list[Model],
                dateFormat: str = "%Y-%m-%d",
                dateRange: list[str] = [],
                delim: Literal[",", "\s+"] = ",",
                riskFactorPositions: list[int] = [],
                riskFreePosition: int = 1) -> None:

        self.path = path
        self.delim = delim
        self.originalData = self.readFile(path, delim, dateFormat, dateRange)

        self.data, self.assetNames = self.getData()
        self.period = self.data.shape[0]

        self.models = models
        self.gammas = gammas
        self.timeHorizon = self.getTimeHorizon(timeHorizon, self.originalData)

        # risk-free asset column
        self.riskFreeReturns = self.getRiskFreeReturns(riskFreePosition)
        # risky asset column, includes risk factor
        self.riskyReturns = self.getRiskyReturns(riskFactorPositions, riskFreePosition)

        self.n = self.riskyReturns.shape[1] + 1

        # number of risky variables
        self.nRisky = self.n - 1
        # total time period
        self.t = len(self.riskyReturns)
        # last time horizon
        self.upperM = self.timeHorizon[-1]

        self.nSubsets = None

        self.initModels()
        self.run()
        
    def getTimeHorizon(self, timeHorizon: list[int], originalData: pd.DataFrame) -> list[int]:        
        # validate time horizon
        if not all(i > originalData.shape[1] for i in timeHorizon):
            raise Exception("Time horizon must be greater than the number of assets")
        
        if not all(i < originalData.shape[0] - 1 for i in timeHorizon):
            raise Exception("Time horizon must be less than the number of columns - 1")
        
        return timeHorizon

    '''
        @brief Read the data file into a pandas DataFrame

        @param path: path to the data file
        @param delim: delimiter for the data file, default is ",", other option is "\s+" for spaces and tabs
        @param dateRange: date range for the data file, default is [], which means no date range

        @return: pandas DataFrame of the data file
    '''
    def readFile(self, path: str, delim: str, dateFormat: str, dateRange: list[str]) -> pd.DataFrame:

        # check if path ends in .csv
        if path[-4:] != ".csv": path = StringIO(path)

        if dateRange != []:
            dateRange = pd.to_datetime(dateRange, exact=False, format=dateFormat)


            date_parser = lambda x: pd.to_datetime(x, format=dateFormat)
            df = pd.read_csv(path, sep=delim, parse_dates=True, index_col=0, date_parser=date_parser)

            mask = (df.index >= dateRange[0]) & (df.index <= dateRange[1])
            new_df = df.loc[mask]
            
            if new_df.empty:
                raise Exception("Date range is not within the range of the data")

            return new_df
        else:
            return pd.read_csv(path, sep=delim, parse_dates=True, index_col=0)

    '''
        @brief Get the data from the pandas DataFrame

        @return: numpy array of the data
        @return: list of asset names
    '''
    def getData(self) -> np.ndarray and list[str]:
        # asset names exclude the risk-free asset
        assetNames = list(self.originalData.columns)
        data = self.originalData.to_numpy()

        return data, assetNames

    '''
        @brief Get the risk-free returns

        @return: numpy array of the risk-free returns
    '''

    def getRiskFreeReturns(self, riskFreePosition:int) -> np.ndarray:
        riskFreePosition -= 1
        if riskFreePosition < 0:
            raise Exception("Risk-free position must be greater than 0")
        if riskFreePosition > self.data.shape[1] - 1:
            raise Exception("Risk-free position must be less than the number of columns")

        return self.data[:, riskFreePosition]

    '''
        @brief Get the risky returns

        @param riskFactorPositions: list of positions of the risk factors in the data file, default is None, start at index 0

        @return: numpy array of the risky returns
        @return: numpy array of the risky returns without the risk factors
    '''

    def getRiskyReturns(self, riskFactor: list, riskFreePosition: int) -> np.ndarray and np.ndarray:
        riskFreePosition -= 1
        riskFactor = [i - 1 for i in riskFactor]
        
        if riskFactor:
            if any(i < 0 for i in riskFactor):
                raise Exception("Risk factor position must be greater than 0")
            if any(i > self.data.shape[1] - 1 for i in riskFactor):
                raise Exception("Risk factor position must be less than the number of columns")

        data = np.delete(self.data, riskFreePosition, 1)

        return data

    '''
        @brief Initalize the models with the following parameters

        @return: None
    '''
    def initModels(self) -> None:
        params = {
            "nRisky": self.nRisky,
            "period": self.period,
            "timeHorizon": self.timeHorizon,
            "riskFreeReturns": self.riskFreeReturns,
            "riskyReturns": self.riskyReturns,
            "gammas": self.gammas,
            "assetNames": self.assetNames
        }

        for model in self.models:
            model.init(params)

    '''
        @brief Get the statistics of the data needed for the models

        @param riskFreeSubset: numpy array of the risk-free returns
        @param riskySubset: numpy array of the risky returns
        @param subset: numpy array of the returns for the given time period
        @param period: time period

        @return: dictionary of the statistics
    '''
    def getStats(self, riskFreeSubset, riskySubset, subset, nPoints) -> dict[str, np.ndarray or float]:
        mu = np.append(np.array([np.mean(riskFreeSubset)]),
                       np.vstack(riskySubset.mean(axis = 0)))
        mu = np.expand_dims(mu, axis = 1)

        totalSigma = np.cov(subset.T)
        sigma = (nPoints - 1) / (nPoints - self.nRisky - 2) * np.cov(riskySubset.T)

        sigmaMLE = (nPoints - 1) / (nPoints) * np.cov(riskySubset.T)
        invSigmaMLE = np.linalg.inv(sigmaMLE)

        amle = np.ones((1, self.nRisky)) @ invSigmaMLE @ np.ones((self.nRisky, 1))

        Y = mu[1:]
        sigmaHat = (nPoints - 1) / (nPoints - self.nRisky - 2) * np.cov(riskySubset.T)
        invSigmaHat = np.linalg.inv(sigmaHat)
        Ahat = np.ones((1, self.nRisky)) @ invSigmaHat @ np.ones((self.nRisky, 1))
        Y0 = (np.ones((1, self.nRisky)) @ invSigmaHat @ Y) / Ahat
        w = (self.nRisky + 2) / ((self.nRisky + 2) + (Y - Y0).T @ (nPoints * invSigmaHat) @ (Y - Y0))
        lamda = (self.nRisky + 2) / ((Y - Y0).T @ invSigmaHat @ (Y - Y0))
        muBS = np.append(np.array([np.mean(riskFreeSubset)]), (1 - w) * Y + w * Y0)
        muBS = np.expand_dims(muBS, axis=1)
        
        sigmaBS = sigmaHat * (1 + 1 / (nPoints + lamda)) + lamda / (nPoints * (nPoints + 1 + lamda)) * np.ones((self.nRisky, 1)) @ np.ones((1, self.nRisky)) / Ahat
        invSigmaBS = np.linalg.inv(sigmaBS)
        totalSigmaBS = (nPoints - 1) / (nPoints - self.nRisky - 2) * totalSigma

        return {
            "mu": mu,
            "sigma": sigma,
            "totalSigma": totalSigma,
            "sigmaMLE": sigmaMLE,
            "invSigmaMLE": invSigmaMLE,
            "amle": amle,

            "Y": Y,
            "sigmaHat": sigmaHat,
            "invSigmaHat": invSigmaHat,
            "Ahat": Ahat,
            "Y0": Y0,
            "w": w,
            "lamda": lamda,
            "muBS": muBS,
            "sigmaBS": sigmaBS,
            "invSigmaBS": invSigmaBS,
            "totalSigmaBS": totalSigmaBS
        }

    '''
        @brief Run the models

        @return: None
    '''
    def run(self) -> None:
        # loop through the time horizon, this is the rolling window
        for currentPeriod in self.timeHorizon:
            period = currentPeriod  # current time horizon
            nPoints = period
            shift = self.upperM - period  # shift in time horizon
            period = period + shift  # update time horizon given shift

            # if period is the same as time currentPeriod, then we only have 1 subset
            self.nSubsets = 1 if period == self.t else self.t - period

            for currentSubset in range(0, self.nSubsets):

                # get the subset of the data
                riskySubset = self.riskyReturns[currentSubset +
                                                shift:period+currentSubset-1, :]
                riskFreeSubset = self.riskFreeReturns[currentSubset +
                                                      shift:period+currentSubset-1]

                # combine the risk-free and risky returns
                subset = np.column_stack((riskFreeSubset, riskySubset))

                stats = self.getStats(riskFreeSubset, riskySubset, subset, nPoints)

                params = stats | {
                    "n": self.n,
                    "gammas": self.gammas,
                    "nRisky": self.nRisky,

                    "period": period,
                    "nPoints": nPoints,
                    "currentSubset": currentSubset,
                    "nSubsets": self.nSubsets,
                }

                for model in self.models:
                    model.runOutSample(params)

    '''
        @brief Get the sharpe ratios of the models

        @return: dictionary of the sharpe ratios
    '''
    def getSharpeRatios(self) -> dict[str, float]:
        sr = {}

        for model in self.models:
            sr[model.name] = model.sharpeRatio()

        return sr

    '''
        @brief Get the statistical significance w.r.t a benchmark of the models

        @param benchmark: out-of-sample returns for a benchmark model

        @return: dictionary of the statistical significance
    '''
    def getStatisticalSignificanceWRTBenchmark(self, benchmark: np.array) -> dict[str, float]:
        sig = {}
        params = {
            "benchmark": benchmark.outSample,
            "nSubsets": self.nSubsets,
            "gammas": self.gammas
        }

        for model in self.models:
            sig[model.name] = model.statisticalSignificanceWRTBenchmark(params)

        return sig
