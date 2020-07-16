from django.db import models
#from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone

class GeoObject(models.Model): #Абстрактный класс объекта с координатами
    name = models.CharField("Название", max_length=256)
    latitude = models.FloatField("Широта")
    longtitude = models.FloatField("Долгота")
    address = models.CharField("Адрес", max_length=512, default='')

    class Meta:
        abstract = True

class Client(GeoObject): #Контрагенты (покупатели)
    ns_code = models.IntegerField("Код NS2000", primary_key=True)
    # name = models.CharField("Название", max_length=256)
    # latitude = models.FloatField("Широта")
    # longtitude = models.FloatField("Долгота")

    class Meta:
        verbose_name_plural = "Контрагенты"
        verbose_name = 'Контрагент'

    def __str__(self):
        return f"{self.ns_code} {self.name}"


class Store(GeoObject): #Склады
    ns_code = models.IntegerField("Код NS2000", primary_key=True)
    # name = models.CharField("Название", max_length=256)
    # latitude = models.FloatField("Широта")
    # longtitude = models.FloatField("Долгота")

    class Meta:
        verbose_name_plural = "Склады"
        verbose_name = 'Склад'

    def __str__(self):
        return f"{self.ns_code} {self.name}"


class RouteSet(models.Model): #История расчетов
    id = models.AutoField("id", primary_key=True)
    creation_date = models.DateTimeField("Дата создания", default=timezone.now)
    username = models.ForeignKey(settings.AUTH_USER_MODEL, default=0, verbose_name="Пользователь", on_delete=models.SET_DEFAULT)
    store = models.ForeignKey(Store, verbose_name="Склад", default=18, on_delete=models.CASCADE)
    comment = models.TextField("Комментарий", default="")

    class Meta:
        indexes = [models.Index(fields=['username', '-id'])]
        verbose_name_plural = "Расчеты маршрутов"
        verbose_name = 'Расчет маршрутов'

    def __str__(self):
        route_stat = RouteStat.objects.get(route_set=self)
        result_str = f"№{self.id} {self.creation_date:%d-%m-%Y %H-%M} скл.{self.store.ns_code} " \
                     f"ТТ {route_stat.get_delivery_dots_count()} "
        if route_stat.reis_count:
            result_str += f"Авто {route_stat.auto_count} Рейсов {route_stat.reis_count} " \
                          f"{'c возвратом' if route_stat.with_return else ''} {'!' if route_stat.high_accuracy else ''}"
        else:
            result_str += "пустой"
        return result_str


    def get_short_desc(self):
        return f"{self.id} {self.creation_date:%d-%m-%Y %H-%M} {self.store.ns_code}"

    def get_unallocated_delivery_dots(self): #Получить список нераспределенных точек (экземпляры RouteInitDot)
        #alloc_dots = RouteDot.objects.filter(route__route_set=self).values('id')
        #unalloc_dots = RouteInitDot.objects.filter(route_set=self).exclude(route_dot_id__in=alloc_dots)
        unalloc_dots = RouteInitDot.objects.filter(route_set=self).filter(route_dot=None)
        return unalloc_dots


class RouteStat(models.Model): #Статистика и параметры расчета
    route_set = models.OneToOneField(RouteSet, verbose_name="Расчет", on_delete=models.CASCADE)

    priority_bad = models.PositiveIntegerField("Нераспределенных приоритетных точек")
    regular_bad = models.PositiveIntegerField("Нераспределенных обычных точек")
    auto_count = models.PositiveIntegerField("Автомобилей использовано")
    reis_count = models.PositiveIntegerField("Рейсов использовано")
    costs = models.PositiveIntegerField("Общие временные затраты (в секундах)")

    with_return = models.BooleanField("Расчет с возвратом на склад", default=False)
    high_accuracy = models.BooleanField("Высокая точность расчета", default=False)
    auto_min = models.BooleanField("Режим минимизации кол-ва авто", default=False)
    early_arrival = models.PositiveIntegerField("На сколько можно приехать раньше окна доставки магазина (кроме приоритетных магазинов)", default=15)
    lately_arrival = models.PositiveIntegerField("На сколько можно приехать позже окна доставки магазина (кроме приоритетных магазинов)", default=15)

    dyn_auto_count_max = models.PositiveIntegerField("Дин.авто: Макс кол-во дин. авто", default=0)
    dyn_auto_capacity = models.PositiveIntegerField("Дин.авто: Емкость", default=0)
    dyn_auto_reis_max = models.PositiveIntegerField("Дин.авто: Макс кол-во рейсов", default=0)
    dyn_auto_driver_limit = models.PositiveIntegerField("Дин.авто: Ограничение смены водителя", default=0)

    class Meta:
        verbose_name_plural = "Статистика расчетов"
        verbose_name = 'Статистика расчета'

    def get_delivery_dots_count(self): #Кол-во распределенных ТТ
        dd_count = 0
        dd_count += RouteInitDot.objects.filter(route_set=self.route_set).count()
        return dd_count

    def get_allocated_delivery_dots_count(self): #Общее кол-во заданных ТТ
        dd_count = 0
        dd_count += RouteDot.objects.filter(route__route_set=self.route_set).count()
        return dd_count


class Route(models.Model): #Маршрут
    route_set = models.ForeignKey(RouteSet, verbose_name="Расчет", on_delete=models.CASCADE)
    graph = models.PositiveIntegerField("Номер графика")
    reis = models.PositiveIntegerField("Номер рейса")
    dyn_auto = models.BooleanField("Использовалось динамическое авто", default=False)
    reis_start = models.PositiveIntegerField("Приезд на погрузку (в секундах с полуночи)")
    load_time = models.PositiveIntegerField("Время погрузки (в секундах)")
    store_return_distance = models.PositiveIntegerField("Расстояние от последней точки до склада (в метрах)", default=0)
    store_return_time = models.PositiveIntegerField("Время возврата на склад от последней точки (в секундах)", default=0)

    class Meta:
        indexes = [models.Index(fields=['route_set', 'graph', 'reis'])]
        verbose_name_plural = "Маршруты"
        verbose_name = 'Маршрут'

    def get_used_capacity(self): #Использованная ёмкость авто
        used_capacity = 0
        delivery_dots = RouteDot.objects.filter(route=self)
        for dot in delivery_dots:
            used_capacity += dot.get_init_dot().quantity
        return used_capacity

    def get_all_distance(self): #Расстояние маршрута
        route_stat = RouteStat.objects.get(route_set=self.route_set)
        all_distance = 0
        delivery_dots = RouteDot.objects.filter(route=self)
        for dot in delivery_dots:
            all_distance += dot.distance
        if route_stat.with_return:  # с возвратом на склад
            all_distance += self.store_return_distance
        return all_distance

    def get_start_time_with_startwait(self): #Время начала рейса(приезда на склад на погрузку) с ожиданием перед ним (если было перенесено время выезда)
        if self.reis == 1: #Для 1 рейса можно просто взять время начала работы водителя
            if not self.dyn_auto:
                reis_start = self.get_auto().reis_start
            else: # Для динамических авто время старта авто = время старта маршрута
                reis_start = self.reis_start
        else: #Для непервых рейсов возьмем время старта = времени окончания предыдущего рейса
            route = Route.objects.get(route_set=self.route_set, graph=self.graph, reis=self.reis-1)
            reis_start = route.reis_start + route.get_all_time()
        return reis_start

    def get_all_time_with_startwait(self): #Общее время, затраченное на рейс с ожиданием перед выездом со склада (если было перенесено время выезда)
        real_reis_start = self.get_start_time_with_startwait()
        reis_time_wo_wait = self.get_all_time()
        all_time_w_wait = reis_time_wo_wait + (self.reis_start - real_reis_start)
        return all_time_w_wait

    def get_all_time(self): #Общее время затраченное на рейс
        route_stat = RouteStat.objects.get(route_set=self.route_set)
        last_dot = RouteDot.objects.filter(route=self).latest('num')
        last_time = last_dot.time_out
        if route_stat.with_return:  # с возвратом на склад
            last_time += self.store_return_time
        all_time = last_time - self.reis_start
        if all_time < 0: all_time = 0
        return all_time

    def get_delivery_dots_count(self):
        dd_count = 0
        dd_count += RouteDot.objects.filter(route=self).count()
        return dd_count

    def get_auto(self): #Получение объекта авто из первоначальных данных
        return RouteInitAuto.objects.filter(route_set=self.route_set).get(num=self.graph)


class RouteDot(models.Model): #Точки маршрута (кроме склада)
    route = models.ForeignKey(Route, verbose_name="Маршрут", on_delete=models.CASCADE)
    num = models.PositiveIntegerField("Номер по порядку в маршруте")
    time_in = models.PositiveIntegerField("Заезд в ТТ(в секундах с полуночи)")
    time_out = models.PositiveIntegerField("Выезд из ТТ(в секундах с полуночи)")
    wait_time = models.PositiveIntegerField("Время ожидания до окна приемки ТТ (в секундах)")
    distance = models.PositiveIntegerField("Расстояние от предыдущей точки маршрута до этой (в метрах)")

    class Meta:
        indexes = [models.Index(fields=['route', 'num'])]
        verbose_name_plural = "Точки маршрутов"
        verbose_name = 'Точка маршрута'

    def get_init_dot(self): #Получение первоначальной точки из исходных данных
        return RouteInitDot.objects.get(route_dot=self)


class RouteInitAuto(models.Model): #Исходные данные: Авто
    route_set = models.ForeignKey(RouteSet, verbose_name="Расчет", on_delete=models.CASCADE)
    num = models.PositiveIntegerField("Порядковый номер (График)")
    name = models.CharField('Гос.Номер', max_length=50)
    capacity = models.FloatField("Емкость авто (лот.)")
    reis_max = models.PositiveIntegerField("Максимальное количество рейсов")
    reis_start = models.PositiveIntegerField("Время начала работы водителя (в секундах с полуночи)")
    reis_start_free = models.BooleanField("Время начала работы водителя не задано", default=False)
    driver_limit = models.PositiveIntegerField("Ограничение смены водителя (в секундах)", default=86400)

    class Meta:
        indexes = [models.Index(fields=['route_set', 'num'])]
        verbose_name_plural = "Исходные авто"
        verbose_name = 'Исходный авто'

    def get_used_driver_limit(self): #Сколько времени из смены было потрачено за весь день работы водителя (авто)
        last_route = Route.objects.filter(route_set=self.route_set).filter(graph=self.num).order_by('-reis')[0]
        start_time = self.reis_start
        end_time = last_route.reis_start + last_route.get_all_time()
        return end_time - start_time

class RouteInitDot(models.Model): #Исходные данные: ТТ
    route_set = models.ForeignKey(RouteSet, verbose_name="Расчет", on_delete=models.CASCADE)
    route_dot = models.OneToOneField(RouteDot, verbose_name="Точка маршрута", on_delete=models.CASCADE, default=None, null=True,)
    client = models.ForeignKey(Client, null=True, verbose_name="Торговая точка", on_delete=models.CASCADE)
    client_name = models.CharField("Название торговой точки", max_length=256)
    client_address = models.TextField("Адрес торговой точки", null=True, default=None)
    latitude = models.FloatField("Широта ТТ", null=True, default=None)
    longtitude = models.FloatField("Долгота ТТ", null=True, default=None)
    quantity = models.FloatField("Заказанное кол-во")
    window_in = models.PositiveIntegerField("Окно приемки в ТТ с (в секундах с полуночи)")
    window_out = models.PositiveIntegerField("Окно приемки в ТТ по (в секундах с полуночи)")
    process_time = models.PositiveIntegerField("Длительность выгрузки в ТТ (в секундах)")
    priority = models.PositiveIntegerField("Приоритет ТТ")

    class Meta:
        verbose_name_plural = "Исходные точки маршрутов"
        verbose_name = 'Исходная точка маршрута'


# class AccessLog(models.Model):
#     host_ip = models.CharField("User IP", max_length=40)
#     host_useragent = models.CharField("Useragent", max_length=200, default="")
#     host_url = models.CharField("URL", max_length=200, default="")
#     access_date = models.DateTimeField(default=timezone.now)
#     log_comment = models.TextField("Admin comment", default="")
#
#     def __str__(self):
#         return self.host_ip + ' ' + self.host_url + ' ' + str(self.access_date)
#
# class CategoryNews(models.Model):
#     name = models.CharField("Название", max_length=100, default='')
#
#     class Meta:
#         verbose_name_plural = "Категории"
#
#     def __str__(self):
#         return self.name
#
# class News(models.Model):
#     title = models.CharField("Заголовок", max_length=100)
#     content = models.TextField("Содержание")
#     creation_date = models.DateTimeField("Дата создания", default=timezone.now)
#     publication_date = models.DateTimeField("Дата публикации", default=timezone.now)
#     category = models.ForeignKey(CategoryNews, default=0, verbose_name="Категория", on_delete=models.SET_DEFAULT)
#
#     class Meta:
#         verbose_name_plural = "Новости"
#
#     def __str__(self):
#         return f"{self.title} ({self.category})"