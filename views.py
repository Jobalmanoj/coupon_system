from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import Coupon
from .serializers import CouponSerializer
from datetime import datetime
from django.db.models import Q
from .models import Coupon, CouponUsage
from rest_framework import status


def compute_cart_value(cart):
    items = cart.get("items", []) or []
    return sum(i.get("unitPrice", 0) * i.get("quantity", 0) for i in items)

def check_eligibility(coupon, user, cart):
    elig = coupon.eligibility or {}
    # user fields
    allowedTiers = elig.get("allowedUserTiers")
    if allowedTiers and user.get("userTier") not in allowedTiers:
        return False

    minLifetimeSpend = elig.get("minLifetimeSpend")
    if minLifetimeSpend is not None and user.get("lifetimeSpend", 0) < minLifetimeSpend:
        return False

    minOrdersPlaced = elig.get("minOrdersPlaced")
    if minOrdersPlaced is not None and user.get("ordersPlaced", 0) < minOrdersPlaced:
        return False

    firstOrderOnly = elig.get("firstOrderOnly")
    if firstOrderOnly and user.get("ordersPlaced", 0) != 0:
        return False

    allowedCountries = elig.get("allowedCountries")
    if allowedCountries and user.get("country") not in allowedCountries:
        return False

    # cart rules
    items = cart.get("items", []) or []
    cart_value = compute_cart_value(cart)
    minCartValue = elig.get("minCartValue")
    if minCartValue is not None and cart_value < minCartValue:
        return False

    minItemsCount = elig.get("minItemsCount")
    if minItemsCount is not None:
        total_items = sum(i.get("quantity", 0) for i in items)
        if total_items < minItemsCount:
            return False

    applicableCategories = elig.get("applicableCategories")
    if applicableCategories:
        if not any(i.get("category") in applicableCategories for i in items):
            return False

    excludedCategories = elig.get("excludedCategories")
    if excludedCategories:
        if any(i.get("category") in excludedCategories for i in items):
            return False

    return True

def compute_discount_amount(coupon, cart):
    cart_value = compute_cart_value(cart)
    dt = coupon.discountType.upper()
    if dt == "FLAT":
        return min(coupon.discountValue, cart_value)
    elif dt == "PERCENT":
        raw = cart_value * (coupon.discountValue / 100.0)
        if coupon.maxDiscountAmount is not None:
            return min(raw, coupon.maxDiscountAmount)
        return raw
    return 0.0

@api_view(['POST'])
def create_coupon(request):
    serializer = CouponSerializer(data=request.data)
    if serializer.is_valid():
        # reject duplicates by default (will raise IntegrityError on save) — serializer handles this
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def list_coupons(request):
    qs = Coupon.objects.all().order_by('-created_at')
    s = CouponSerializer(qs, many=True)
    return Response(s.data)

@api_view(['POST'])
def best_coupon(request):
    payload = request.data
    user = payload.get("user")
    cart = payload.get("cart")
    if not user or not cart:
        return Response({"error": "user and cart required"}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    # fetch only currently valid coupons
    qs = Coupon.objects.filter(startDate__lte=now, endDate__gte=now)
    candidates = []
    for c in qs:
        # Note: usageLimitPerUser enforcement should be handled with a usage table; placeholder skip for now.
        if not check_eligibility(c, user, cart):
            continue
        discount = compute_discount_amount(c, cart)
        if discount <= 0:
            continue
        candidates.append({
            "coupon": c,
            "discount": round(discount, 2)
        })

    if not candidates:
        return Response({"bestCoupon": None})

    # Pick best: highest discount, then earliest endDate, then lexicographically smaller code
    candidates.sort(key=lambda e: (-e["discount"], e["coupon"].endDate, e["coupon"].code))
    best = candidates[0]
    return Response({
        "bestCoupon": {
            "code": best["coupon"].code,
            "discount": best["discount"],
            "endDate": best["coupon"].endDate,
            "description": best["coupon"].description
        }
    })
from django.db import transaction

@api_view(['POST'])
def apply_coupon(request):
    """
    Apply a coupon for a user and record usage.
    Body: { "user": {...}, "code": "WELCOME100", "cart": {...} }
    """
    body = request.data
    user = body.get("user")
    code = body.get("code")
    cart = body.get("cart", {"items": []})

    if not user or not code:
        return Response({"error": "user and code required"}, status=status.HTTP_400_BAD_REQUEST)

    userId = user.get("userId")
    if not userId:
        return Response({"error": "user must include userId"}, status=status.HTTP_400_BAD_REQUEST)

    # find coupon
    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return Response({"error": "coupon not found"}, status=status.HTTP_404_NOT_FOUND)

    # check date validity
    now = timezone.now()
    if not (coupon.startDate <= now <= coupon.endDate):
        return Response({"error": "coupon not valid at this time"}, status=status.HTTP_400_BAD_REQUEST)

    # eligibility check
    if not check_eligibility(coupon, user, cart):
        return Response({"error": "user/cart not eligible for coupon"}, status=status.HTTP_400_BAD_REQUEST)

    # compute discount
    discount = compute_discount_amount(coupon, cart)
    if discount <= 0:
        return Response({"error": "coupon gives zero discount for this cart"}, status=status.HTTP_400_BAD_REQUEST)

    # enforce usageLimitPerUser safely
    with transaction.atomic():
        if coupon.usageLimitPerUser:
            used_count = CouponUsage.objects.select_for_update().filter(
                coupon=coupon, user_id=userId
            ).count()

            if used_count >= coupon.usageLimitPerUser:
                return Response({"error": "usage limit exceeded for this user"}, status=status.HTTP_400_BAD_REQUEST)

        # record usage
        CouponUsage.objects.create(coupon=coupon, user_id=userId)

    return Response({
        "applied": coupon.code,
        "discount": round(discount, 2)
    }, status=status.HTTP_200_OK)

