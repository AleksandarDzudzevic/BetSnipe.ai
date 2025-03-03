# Arbitrage Betting Telegram bot

An advanced Python-based system that scrapes betting odds from multiple Serbian bookmakers, identifies arbitrage opportunities in real-time, and automatically notifies users via Telegram. This tool helps find profitable betting opportunities across different bookmakers by analyzing odds discrepancies.

## 🎯 Key Features

### Data Collection
- Asynchronous scraping of multiple betting sites simultaneously
- Real-time odds monitoring and updates
- Support for multiple sports:
  - Football (Soccer)
  - Basketball
  - Hockey
  - Tennis
  - Table Tennis

### Analysis
- Automated arbitrage opportunity detection
- Cross-bookmaker odds comparison
- Real-time calculation of potential profits
- Multi-way arbitrage calculations

### Notifications
- Instant Telegram notifications for profitable opportunities
- Customizable profit threshold alerts
- Detailed bet placement instructions
- Quick links to relevant bookmaker pages

### Data Management
- SQL Server database integration
- CSV file generation for each sport
- Historical data tracking
- Automated data cleanup

## 🏢 Supported Bookmakers

- Admiral
- Soccerbet
- Meridian
- Maxbet
- Superbet
- Mozzart
- Merkur
- Balkanbet
- Pinnbet
- 1xBet
- Topbet

## 💹 Arbitrage Calculation

The system calculates arbitrage opportunities using the following approach:
1. Cross-comparison of odds across bookmakers
2. Calculation of implied probabilities
3. Identification of positive expected value opportunities
4. Optimal stake distribution calculations

## 🤖 Telegram Bot Features

- Real-time arbitrage notifications
- Customizable alert thresholds
- Detailed betting instructions including:
  - Bookmaker names
  - Event details
  - Recommended stake distribution
  - Expected profit percentage
- Quick access links to betting pages

## ⚠️ Risk Management

- Data validation and verification
- Connection error handling
- Rate limiting compliance
- Automated recovery mechanisms
- Continuous monitoring and logging

## 📊 Performance Monitoring

- Success rate tracking
- Response time monitoring
- Error rate analysis
- System health checks

## 🔒 Security Considerations

- Secure database connections
- Environment variable protection
- API rate limit compliance
- IP rotation capability


## 📝 License

[MIT](https://choosealicense.com/licenses/mit/)

## ⚠️ Disclaimer

This tool is for educational purposes only. Please ensure compliance with local gambling laws and bookmaker terms of service before use.
