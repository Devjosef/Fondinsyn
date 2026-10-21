### ETL pipeline automates the quarterly extraction, transformation, and loading of holdings data from multiple Swedish index funds.

**Project Overview**
This project automates the quarterly extraction, transformation, and loading of holdings data from a small subset of Swedish index funds. It focuses on consolidating portfolio holdings by sector and market capitalization to give investors and analysts useful insights into what funds hold.

**Purpose**
To simplify gathering holdings info from different funds, changing raw asset data into grouped sectors and market caps. This makes it easier to compare, spot trends, analyze risks, and make smarter investment choices.


**ETL Pipeline**
• Extract: Automatically grabs holdings data (stocks, weights) from Swedish index funds every quarter using Finansinspektionen's zipped XML files.
• Transform: Cleans the data and group holdings by sector, market cap, or other useful categories.
• Load: Put the cleaned and grouped data into a database or dashboard so it’s easy to see, report on, and analyze.

### Usage
1. Run the extraction script to download the latest quarterly holdings files from Finansinspektionen.

2. Run the transformation steps to group holdings by sector and market cap.

3. Load the results into a dashboard or database for easy comparison and visualization.

### Tech Stack

Python (ETL scripts and data manipulation)

Pandas & PyYAML (data handling/config)

PostgreSQL / SQLite (data storage)

Docker (deployment and database environment)

**Expected Conclusion**
Investors, analysts, and portfolio managers get an up-to-date, clear view of how Swedish index funds are composed each quarter. This makes comparing funds easier by aiding understanding of sector & market risks better. The setup cuts down on manual work and gives timely, standardized insights to back investment decisions. 

**Final Conclusion**
The ETL pipeline successfully extracted 1.35M holdings from 8,976 XML files across 892 Swedish index funds, transformed them into 59,312 fund × sector × quarter allocations, and loaded them into PostgreSQL. The database now contains 28,437 unique securities categorized into 7 sectors. Work is still left to be done: we need to get it to Tableau or Power BI, and optionally automated validation of the extracted data using a CI.

