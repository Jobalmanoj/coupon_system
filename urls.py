from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_coupon, name='create_coupon'),
    path('list/', views.list_coupons, name='list_coupons'),
    path('best/', views.best_coupon, name='best_coupon'),
    path('apply/', views.apply_coupon, name='apply_coupon'),

]
