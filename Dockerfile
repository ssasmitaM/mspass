#Image: wangyinz/mspass
#Version: 0.0.1

FROM mongo:4.2.0

MAINTAINER Ian Wang <yinzhi.wang.cug@gmail.com>

RUN apt-get update \
    && apt-get install -y wget python3-setuptools \
       build-essential python3-dev python3-pip openjdk-11-jdk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* 

RUN pip3 --no-cache-dir install pymongo

# Prepare the environment
ENV SPARK_VERSION 2.4.3

ENV JAVA_HOME /usr/lib/jvm/java-11-openjdk-amd64
ENV SPARK_HOME /usr/local/spark

ENV APACHE_MIRROR http://ftp.ps.pl/pub/apache
ENV SPARK_URL ${APACHE_MIRROR}/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop2.7.tgz

# Download & install Spark
RUN wget -qO - ${SPARK_URL} | tar -xz -C /usr/local/ \
    && cd /usr/local && ln -s spark-${SPARK_VERSION}-bin-hadoop2.7 spark

