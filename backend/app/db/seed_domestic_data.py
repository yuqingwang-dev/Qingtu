"""Seed a first batch of domestic cities and POIs for the China-first MVP."""
from __future__ import annotations

from datetime import time

from app.db.models import Activity, City
from app.db.session import SessionLocal


DOMESTIC_CITY_DATA = [
    {
        "name": "Beijing",
        "name_zh": "北京",
        "country": "China",
        "country_zh": "中国",
        "time_zone": "Asia/Shanghai",
        "default_currency": "CNY",
        "latitude": 39.9042,
        "longitude": 116.4074,
        "activities": [
            {"name": "Forbidden City", "name_zh": "故宫博物院", "category": "culture", "cost": 60, "duration": 240, "rating": 4.8, "latitude": 39.9163, "longitude": 116.3972, "open_time": time(8, 30), "close_time": time(17, 0), "description": "Imperial palace complex in central Beijing.", "description_zh": "北京最核心的皇家宫殿群，适合首次来北京时重点安排。"},
            {"name": "Temple of Heaven", "name_zh": "天坛公园", "category": "culture", "cost": 34, "duration": 120, "rating": 4.7, "latitude": 39.8822, "longitude": 116.4065, "open_time": time(6, 0), "close_time": time(22, 0), "description": "Historic religious complex used by Ming and Qing emperors.", "description_zh": "大型历史皇家祭祀建筑群，适合散步和感受古建筑。"},
            {"name": "Summer Palace", "name_zh": "颐和园", "category": "nature", "cost": 60, "duration": 210, "rating": 4.8, "latitude": 39.9997, "longitude": 116.2755, "open_time": time(6, 30), "close_time": time(20, 0), "description": "Lakeside imperial garden with long walking routes.", "description_zh": "皇家园林景区，面积大、景色好，但步行量也比较大。"},
            {"name": "Nanluoguxiang", "name_zh": "南锣鼓巷", "category": "shopping", "cost": 80, "duration": 120, "rating": 4.3, "latitude": 39.9375, "longitude": 116.4039, "open_time": time(10, 0), "close_time": time(22, 0), "description": "Popular hutong area with snacks and boutiques.", "description_zh": "胡同风格街区，适合边走边吃、逛小店。"},
            {"name": "The Palace Museum East Gate Snacks", "name_zh": "故宫东华门周边小吃", "category": "food", "cost": 70, "duration": 75, "rating": 4.4, "latitude": 39.9212, "longitude": 116.4075, "open_time": time(10, 30), "close_time": time(20, 30), "description": "Snack cluster near the Forbidden City.", "description_zh": "适合从故宫出来后就近补一顿，节省绕路时间。"},
            {"name": "798 Art District", "name_zh": "798 艺术区", "category": "culture", "cost": 30, "duration": 150, "rating": 4.5, "latitude": 39.9841, "longitude": 116.4971, "open_time": time(10, 0), "close_time": time(18, 0), "description": "Modern art district with galleries and cafes.", "description_zh": "北京现代艺术氛围很强的区域，适合喜欢拍照和展览的人。"},
            {"name": "Jingshan Park", "name_zh": "景山公园", "category": "nature", "cost": 10, "duration": 60, "rating": 4.6, "latitude": 39.9295, "longitude": 116.3955, "open_time": time(6, 0), "close_time": time(21, 0), "description": "Hilltop park with a view over the Forbidden City.", "description_zh": "俯瞰故宫全景很经典，适合与故宫安排在同一天。"},
            {"name": "Wangfujing Pedestrian Street", "name_zh": "王府井步行街", "category": "shopping", "cost": 120, "duration": 120, "rating": 4.2, "latitude": 39.9155, "longitude": 116.4111, "open_time": time(10, 0), "close_time": time(22, 0), "description": "Busy shopping street in central Beijing.", "description_zh": "北京市中心热门商圈，适合买东西和吃饭。"},
            {"name": "Beihai Park", "name_zh": "北海公园", "category": "nature", "cost": 20, "duration": 90, "rating": 4.5, "latitude": 39.9308, "longitude": 116.3897, "open_time": time(6, 30), "close_time": time(21, 0), "description": "Historic lake park close to central Beijing attractions.", "description_zh": "中心城区经典公园，适合作为轻松行程的一站。"},
            {"name": "Ghost Street Dinner", "name_zh": "簋街晚餐", "category": "food", "cost": 150, "duration": 90, "rating": 4.4, "latitude": 39.9417, "longitude": 116.4196, "open_time": time(11, 0), "close_time": time(23, 30), "description": "Well-known dining strip for Beijing-style dinners.", "description_zh": "北京夜间吃饭选择很多的一条街，适合晚上收尾。"},
        ],
    },
    {
        "name": "Shanghai",
        "name_zh": "上海",
        "country": "China",
        "country_zh": "中国",
        "time_zone": "Asia/Shanghai",
        "default_currency": "CNY",
        "latitude": 31.2304,
        "longitude": 121.4737,
        "activities": [
            {"name": "The Bund", "name_zh": "外滩", "category": "culture", "cost": 0, "duration": 90, "rating": 4.8, "latitude": 31.2400, "longitude": 121.4900, "open_time": None, "close_time": None, "description": "Historic waterfront promenade with skyline views.", "description_zh": "上海最经典的滨江地标，适合第一次来上海必打卡。"},
            {"name": "Yu Garden", "name_zh": "豫园", "category": "culture", "cost": 40, "duration": 120, "rating": 4.5, "latitude": 31.2273, "longitude": 121.4924, "open_time": time(9, 0), "close_time": time(16, 30), "description": "Classical Chinese garden in the old town.", "description_zh": "老城厢里非常代表性的江南园林，适合搭配城隍庙一起逛。"},
            {"name": "Nanjing Road", "name_zh": "南京路步行街", "category": "shopping", "cost": 120, "duration": 120, "rating": 4.4, "latitude": 31.2344, "longitude": 121.4753, "open_time": time(10, 0), "close_time": time(22, 0), "description": "Major shopping street in central Shanghai.", "description_zh": "上海热门商圈，适合购物、逛街和吃饭。"},
            {"name": "Lujiazui Skyline", "name_zh": "陆家嘴", "category": "culture", "cost": 60, "duration": 120, "rating": 4.7, "latitude": 31.2354, "longitude": 121.4998, "open_time": None, "close_time": None, "description": "Modern skyline district across the river from the Bund.", "description_zh": "上海城市天际线核心区域，适合看高楼和夜景。"},
            {"name": "Shanghai Tower Observation Deck", "name_zh": "上海中心观光厅", "category": "culture", "cost": 180, "duration": 90, "rating": 4.7, "latitude": 31.2336, "longitude": 121.5055, "open_time": time(9, 0), "close_time": time(21, 0), "description": "High observation deck with panoramic city views.", "description_zh": "适合想一次看全上海城市景观的人。"},
            {"name": "Wukang Road", "name_zh": "武康路", "category": "culture", "cost": 30, "duration": 90, "rating": 4.6, "latitude": 31.2047, "longitude": 121.4384, "open_time": None, "close_time": None, "description": "Tree-lined historic street with cafes and architecture.", "description_zh": "适合慢慢散步、看老建筑、拍照和找咖啡馆。"},
            {"name": "Xintiandi", "name_zh": "新天地", "category": "shopping", "cost": 180, "duration": 120, "rating": 4.5, "latitude": 31.2206, "longitude": 121.4758, "open_time": time(10, 0), "close_time": time(23, 0), "description": "Stylish pedestrian district for dining and nightlife.", "description_zh": "适合晚上吃饭、逛街和感受都市氛围。"},
            {"name": "Tianzifang", "name_zh": "田子坊", "category": "shopping", "cost": 80, "duration": 90, "rating": 4.2, "latitude": 31.2108, "longitude": 121.4662, "open_time": time(10, 0), "close_time": time(21, 0), "description": "Lane-style arts and crafts district.", "description_zh": "适合喜欢弄堂、小店和轻松逛街的人。"},
            {"name": "Jing'an Temple", "name_zh": "静安寺", "category": "culture", "cost": 50, "duration": 60, "rating": 4.5, "latitude": 31.2231, "longitude": 121.4450, "open_time": time(7, 30), "close_time": time(17, 0), "description": "Downtown Buddhist temple surrounded by modern shopping.", "description_zh": "位于市中心，适合与静安寺商圈一并安排。"},
            {"name": "People's Square", "name_zh": "人民广场", "category": "nature", "cost": 0, "duration": 60, "rating": 4.3, "latitude": 31.2304, "longitude": 121.4737, "open_time": None, "close_time": None, "description": "Central civic square near museums and shopping streets.", "description_zh": "交通方便，是衔接市中心多个点位的中转区域。"},
            {"name": "City God Temple Snacks", "name_zh": "城隍庙小吃", "category": "food", "cost": 85, "duration": 75, "rating": 4.3, "latitude": 31.2277, "longitude": 121.4929, "open_time": time(10, 0), "close_time": time(21, 30), "description": "Traditional Shanghai snacks around Yu Garden.", "description_zh": "适合和豫园放在一起安排，顺路解决一餐。"},
        ],
    },
    {
        "name": "Hangzhou",
        "name_zh": "杭州",
        "country": "China",
        "country_zh": "中国",
        "time_zone": "Asia/Shanghai",
        "default_currency": "CNY",
        "latitude": 30.2741,
        "longitude": 120.1551,
        "activities": [
            {"name": "West Lake", "name_zh": "西湖", "category": "nature", "cost": 0, "duration": 180, "rating": 4.9, "latitude": 30.2431, "longitude": 120.1500, "open_time": None, "close_time": None, "description": "Famous lake scenery and classic Hangzhou landmark.", "description_zh": "杭州最核心的景点，适合第一次来杭州作为主线安排。"},
            {"name": "Lingyin Temple", "name_zh": "灵隐寺", "category": "culture", "cost": 75, "duration": 150, "rating": 4.8, "latitude": 30.2426, "longitude": 120.1016, "open_time": time(6, 30), "close_time": time(18, 0), "description": "Historic temple complex in a wooded valley.", "description_zh": "非常有代表性的寺庙景区，适合想看山林和古寺的人。"},
            {"name": "Longjing Village", "name_zh": "龙井村", "category": "nature", "cost": 60, "duration": 120, "rating": 4.6, "latitude": 30.2260, "longitude": 120.1160, "open_time": time(8, 0), "close_time": time(18, 0), "description": "Tea village known for Longjing tea and green hills.", "description_zh": "适合体验杭州茶文化，也适合轻松散步。"},
            {"name": "Hefang Street", "name_zh": "河坊街", "category": "shopping", "cost": 90, "duration": 120, "rating": 4.3, "latitude": 30.2419, "longitude": 120.1706, "open_time": time(10, 0), "close_time": time(22, 0), "description": "Old street with snacks, souvenirs, and local culture.", "description_zh": "适合买特产、吃小吃，比较适合晚上安排。"},
            {"name": "Leifeng Pagoda", "name_zh": "雷峰塔", "category": "culture", "cost": 40, "duration": 75, "rating": 4.5, "latitude": 30.2263, "longitude": 120.1487, "open_time": time(8, 0), "close_time": time(20, 0), "description": "Pagoda overlooking the southern side of West Lake.", "description_zh": "适合与西湖南线一起安排，视野不错。"},
            {"name": "Hubin Road", "name_zh": "湖滨步行街", "category": "shopping", "cost": 120, "duration": 90, "rating": 4.4, "latitude": 30.2571, "longitude": 120.1634, "open_time": time(10, 0), "close_time": time(22, 30), "description": "Busy commercial area near the lake.", "description_zh": "适合收尾逛街、吃饭，位置也比较方便。"},
            {"name": "Zhongshan Road Snack Stop", "name_zh": "中山南路小吃", "category": "food", "cost": 60, "duration": 60, "rating": 4.4, "latitude": 30.2401, "longitude": 120.1741, "open_time": time(11, 0), "close_time": time(21, 0), "description": "Casual stop for Hangzhou-style snacks.", "description_zh": "适合穿插在老城区行程中，当作补给点。"},
            {"name": "China National Tea Museum", "name_zh": "中国茶叶博物馆", "category": "culture", "cost": 20, "duration": 90, "rating": 4.5, "latitude": 30.2193, "longitude": 120.1175, "open_time": time(9, 0), "close_time": time(17, 0), "description": "Museum dedicated to Chinese tea culture.", "description_zh": "适合想更系统了解茶文化的人。"},
            {"name": "Qinghefang Night Walk", "name_zh": "清河坊夜游", "category": "culture", "cost": 40, "duration": 75, "rating": 4.2, "latitude": 30.2416, "longitude": 120.1708, "open_time": time(18, 0), "close_time": time(22, 30), "description": "Evening stroll through the old commercial quarter.", "description_zh": "适合作为晚上轻松散步的收尾路线。"},
            {"name": "Prince Bay Park", "name_zh": "太子湾公园", "category": "nature", "cost": 0, "duration": 60, "rating": 4.6, "latitude": 30.2360, "longitude": 120.1445, "open_time": None, "close_time": None, "description": "Scenic park popular in spring and autumn.", "description_zh": "适合轻松散步和赏景，节奏比热门景区更松。"},
        ],
    },
    {
        "name": "Chengdu",
        "name_zh": "成都",
        "country": "China",
        "country_zh": "中国",
        "time_zone": "Asia/Shanghai",
        "default_currency": "CNY",
        "latitude": 30.5728,
        "longitude": 104.0668,
        "activities": [
            {"name": "Chengdu Research Base of Giant Panda Breeding", "name_zh": "成都大熊猫繁育研究基地", "category": "nature", "cost": 55, "duration": 180, "rating": 4.8, "latitude": 30.7334, "longitude": 104.1457, "open_time": time(7, 30), "close_time": time(18, 0), "description": "Famous panda conservation base.", "description_zh": "成都最有代表性的热门景点之一，适合早一点去。"},
            {"name": "Jinli Ancient Street", "name_zh": "锦里古街", "category": "shopping", "cost": 80, "duration": 120, "rating": 4.4, "latitude": 30.6484, "longitude": 104.0498, "open_time": time(10, 0), "close_time": time(22, 30), "description": "Old-style lane with snacks and souvenirs.", "description_zh": "适合吃小吃、买伴手礼、感受成都老街氛围。"},
            {"name": "Wuhou Shrine", "name_zh": "武侯祠", "category": "culture", "cost": 50, "duration": 90, "rating": 4.6, "latitude": 30.6463, "longitude": 104.0484, "open_time": time(9, 0), "close_time": time(18, 0), "description": "Historic shrine tied to the Three Kingdoms era.", "description_zh": "适合喜欢三国文化和历史的人。"},
            {"name": "Kuanzhai Alley", "name_zh": "宽窄巷子", "category": "shopping", "cost": 100, "duration": 120, "rating": 4.3, "latitude": 30.6668, "longitude": 104.0491, "open_time": time(10, 0), "close_time": time(22, 0), "description": "Popular alley district with food and local shops.", "description_zh": "适合轻松逛街和体验成都慢生活。"},
            {"name": "People's Park Tea House", "name_zh": "人民公园喝茶", "category": "food", "cost": 58, "duration": 90, "rating": 4.6, "latitude": 30.6619, "longitude": 104.0560, "open_time": time(9, 0), "close_time": time(19, 0), "description": "Tea house experience in central Chengdu.", "description_zh": "非常适合感受成都本地休闲节奏。"},
            {"name": "IFS Panda Landmark", "name_zh": "IFS 熊猫地标", "category": "shopping", "cost": 0, "duration": 45, "rating": 4.4, "latitude": 30.6596, "longitude": 104.0823, "open_time": None, "close_time": None, "description": "City-center panda landmark and shopping area.", "description_zh": "适合作为市中心打卡点，停留时间不用太长。"},
            {"name": "Chunxi Road", "name_zh": "春熙路", "category": "shopping", "cost": 150, "duration": 120, "rating": 4.4, "latitude": 30.6590, "longitude": 104.0822, "open_time": time(10, 0), "close_time": time(22, 30), "description": "Busy shopping district in downtown Chengdu.", "description_zh": "适合购物、吃饭和晚上收尾。"},
            {"name": "Du Fu Thatched Cottage", "name_zh": "杜甫草堂", "category": "culture", "cost": 50, "duration": 90, "rating": 4.5, "latitude": 30.6664, "longitude": 103.9966, "open_time": time(9, 0), "close_time": time(18, 0), "description": "Historic memorial site for poet Du Fu.", "description_zh": "适合喜欢文学和园林环境的人。"},
            {"name": "Hotpot Dinner", "name_zh": "成都火锅", "category": "food", "cost": 160, "duration": 90, "rating": 4.7, "latitude": 30.6570, "longitude": 104.0703, "open_time": time(11, 0), "close_time": time(23, 0), "description": "Classic Chengdu hotpot experience.", "description_zh": "来成都非常适合作为一天结束的一顿重头戏。"},
            {"name": "Anshun Bridge Night View", "name_zh": "安顺廊桥夜景", "category": "culture", "cost": 20, "duration": 45, "rating": 4.4, "latitude": 30.6477, "longitude": 104.0882, "open_time": None, "close_time": None, "description": "Popular riverside night-view spot.", "description_zh": "适合晚上散步收尾，拍照效果不错。"},
        ],
    },
]


def _upsert_city(db, city_data: dict) -> City:
    city = db.query(City).filter(City.name == city_data["name"]).first()
    if city is None:
        city = City(
            name=city_data["name"],
            name_zh=city_data["name_zh"],
            country=city_data["country"],
            country_zh=city_data["country_zh"],
            time_zone=city_data["time_zone"],
            default_currency=city_data["default_currency"],
            latitude=city_data["latitude"],
            longitude=city_data["longitude"],
            is_domestic=True,
        )
        db.add(city)
        db.flush()

    city.name_zh = city_data["name_zh"]
    city.country = city_data["country"]
    city.country_zh = city_data["country_zh"]
    city.time_zone = city_data["time_zone"]
    city.default_currency = city_data["default_currency"]
    city.latitude = city_data["latitude"]
    city.longitude = city_data["longitude"]
    city.is_domestic = True
    return city


def _upsert_activity(db, city_id: int, item: dict) -> None:
    activity = (
        db.query(Activity)
        .filter(Activity.city_id == city_id, Activity.name == item["name"])
        .first()
    )
    if activity is None:
        activity = Activity(city_id=city_id, name=item["name"], category=item["category"])
        db.add(activity)

    activity.name_zh = item["name_zh"]
    activity.category = item["category"]
    activity.base_cost = item["cost"]
    activity.avg_duration_minutes = item["duration"]
    activity.rating = item["rating"]
    activity.latitude = item["latitude"]
    activity.longitude = item["longitude"]
    activity.open_time = item["open_time"]
    activity.close_time = item["close_time"]
    activity.description = item["description"]
    activity.description_zh = item["description_zh"]


def seed_domestic_data() -> None:
    db = SessionLocal()
    try:
        for city_data in DOMESTIC_CITY_DATA:
            city = _upsert_city(db, city_data)
            db.flush()
            for activity_data in city_data["activities"]:
                _upsert_activity(db, city.id, activity_data)
        db.commit()
        print("Domestic city seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_domestic_data()
